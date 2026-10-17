import ast
import asyncio
import inspect
import logging
import math
import operator
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Literal, Optional, Tuple

from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ConfigDict, Field

from backend.app.services.cancellation import cancellation_service, OperationCancelledError
from backend.app.services.chat import chat_service
from backend.app.services.document import document_service
from backend.app.services.search import search_service
from backend.app.services.progress import progress_service

logger = logging.getLogger(__name__)


class ComplexityDecision(BaseModel):
    level: Literal["simple", "complex"] = Field(
        description="Whether the question is simple enough for direct answering."
    )
    rationale: str = Field(description="Short explanation for the classification.")


class PlanTask(BaseModel):
    task_name: str = Field(description="A short name for the task.")
    objective: str = Field(description="What this task must accomplish.")
    requires_vector_search: bool = Field(
        description="Whether document retrieval is required.", default=False
    )
    requires_tool: bool = Field(
        description="Whether an external tool is required for this task.",
        default=False,
    )
    tool_name: Optional[str] = Field(
        default=None,
        description="Name of the tool to call when requires_tool is true. Supported values include 'web_search' and 'calculator'.",
    )
    tool_arguments: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional arguments for the selected tool. For example {'query': 'latest market size data'} for web_search.",
    )
    model_preference: Literal["general", "reasoning"] = Field(
        description="Preferred model class. Use 'general' for knowledge tasks and 'reasoning' for logical tasks.",
        default="general",
    )
    model_config = ConfigDict(protected_namespaces=())


class PlanOutput(BaseModel):
    overall_strategy: str = Field(description="Summary of the research approach.")
    tasks: List[PlanTask] = Field(description="Ordered list of tasks.")


class IterationDecision(BaseModel):
    status: Literal["complete", "iterate"] = Field(
        description="Whether the workflow can finish or should iterate again."
    )
    reason: str = Field(description="Explanation for the decision.")
    missing_information: Optional[List[str]] = Field(
        default=None, description="Key information that still needs to be gathered."
    )


@dataclass(frozen=True)
class ModelTier:
    general: str
    reasoning: str


class DeepResearchService:
    """
    LangChain based deep-research workflow:
      1. Classify the incoming question.
      2. Plan tasks for complex questions.
      3. Execute tasks sequentially with optional document retrieval.
      4. Synthesize results and decide if another iteration is required.
    """

    provider_models: Dict[str, ModelTier] = {
        "deepseek": ModelTier(general="deepseek-chat", reasoning="deepseek-reasoner"),
        "deepseek-reasoner": ModelTier(general="deepseek-reasoner", reasoning="deepseek-reasoner"),
        "qwen": ModelTier(general="qwen-max", reasoning="qwq-plus"),
        "gpt": ModelTier(general="gpt-5", reasoning="gpt-5-mini"),
        "gemini": ModelTier(general="gemini-2.5-pro", reasoning="gemini-2.5-flash"),
        "grok": ModelTier(general="grok-4-0709", reasoning="grok-3-mini"),
        "custom": ModelTier(general="", reasoning=""),
        "local": ModelTier(general="", reasoning=""),
    }

    max_iterations: int = 3

    def __init__(self) -> None:
        # 获取默认配置（优先使用chat_service的配置）
        raw_api_key = getattr(chat_service.cloud_client, "api_key", None)
        raw_base_url = getattr(chat_service.cloud_client, "base_url", None)

        self.api_key = raw_api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = (
            str(raw_base_url) if raw_base_url is not None else os.getenv("OPENAI_BASE_URL")
        )

        # DashScope配置（用于Qwen模型）
        self.dashscope_api_key = os.getenv("DASHSCOPE_API_KEY", "")
        self.dashscope_base_url = os.getenv("DASHSCOPE_BASE_URL", "")

        if not self.api_key or not self.base_url:
            logger.warning(
                "Missing API key or base URL. Deep research workflow may fail when calling LLMs."
            )

        self._complexity_parser = JsonOutputParser(pydantic_object=ComplexityDecision)
        self._plan_parser = JsonOutputParser(pydantic_object=PlanOutput)
        self._iteration_parser = JsonOutputParser(pydantic_object=IterationDecision)
        self._str_parser = StrOutputParser()
        self._tool_handlers: Dict[str, Callable[[PlanTask], Awaitable[Dict[str, Any]]]] = {
            "web_search": self._tool_web_search,
            "calculator": self._tool_calculator,
        }
        self._math_binary_ops = {
            ast.Add: operator.add,
            ast.Sub: operator.sub,
            ast.Mult: operator.mul,
            ast.Div: operator.truediv,
            ast.Pow: operator.pow,
            ast.Mod: operator.mod,
        }
        self._math_unary_ops = {
            ast.UAdd: lambda value: value,
            ast.USub: lambda value: -value,
        }
        self._math_functions = {
            name: getattr(math, name)
            for name in ("sqrt", "log", "log10", "exp", "sin", "cos", "tan", "asin", "acos", "atan")
        }
        # 用于存储等待用户确认的计划
        self._pending_plans: Dict[str, Dict[str, Any]] = {}
        # 用于等待用户确认的事件
        self._plan_approval_events: Dict[str, asyncio.Event] = {}

    def approve_plan(self, progress_id: str, revised_plan: Dict[str, Any]) -> bool:
        """
        接收用户修订的计划并继续工作流

        Args:
            progress_id: 进度ID
            revised_plan: 用户修订后的计划，包含 overall_strategy 和 tasks

        Returns:
            是否成功接收计划
        """
        if progress_id not in self._pending_plans:
            logger.warning("No pending plan found for progress_id=%s", progress_id)
            return False

        try:
            # 验证并存储修订后的计划
            self._pending_plans[progress_id]["revised_plan"] = revised_plan

            # 触发事件，让等待的协程继续执行
            if progress_id in self._plan_approval_events:
                self._plan_approval_events[progress_id].set()
                logger.info("Plan approved for progress_id=%s", progress_id)
                return True
            else:
                logger.warning("No approval event found for progress_id=%s", progress_id)
                return False
        except Exception as e:
            logger.error("Failed to approve plan for progress_id=%s: %s", progress_id, str(e))
            return False

    async def run_workflow(
        self,
        question: str,
        llm_type: Literal["deepseek", "deepseek-reasoner", "qwen", "gpt", "gemini", "grok", "custom", "local"] = "deepseek",
        progress_id: Optional[str] = None,
        cancel_tokens: Optional[List[Optional[str]]] = None,
        cloud_config: Optional[Dict[str, Any]] = None,
        max_iterations: Optional[int] = None,
        library_type: Optional[str] = None,
        knowledge_group_ids: Optional[List[str]] = None,
        enable_web_search: bool = False,
        enable_rag: bool = False,
    ) -> Dict[str, Any]:
        cancel_tokens_list = [token for token in (cancel_tokens or []) if token]
        provider_key = self._normalize_provider(llm_type)
        if provider_key == "local":
            raise ValueError("Deep research mode does not support local models yet.")

        # 根据provider选择对应的API配置
        if provider_key == "qwen":
            # Qwen模型使用DashScope配置
            default_api_key = self.dashscope_api_key
            default_base_url = self.dashscope_base_url
        else:
            # 其他模型使用通用配置
            default_api_key = self.api_key
            default_base_url = self.base_url

        runtime_api_key = (cloud_config or {}).get("api_key") or default_api_key
        runtime_base_url = (cloud_config or {}).get("base_url") or default_base_url
        if not runtime_api_key or not runtime_base_url:
            raise ValueError(f"请先配置{llm_type}模型的 API KEY 和 Base URL。")

        base_tier = self.provider_models.get(provider_key, ModelTier(general="", reasoning=""))
        runtime_general = (cloud_config or {}).get("general_model") or base_tier.general
        runtime_reasoning = (cloud_config or {}).get("reasoning_model") or base_tier.reasoning
        if not runtime_general or not runtime_reasoning:
            raise ValueError("深度研究需要同时配置通用模型与推理模型名称。")
        active_tier = ModelTier(general=runtime_general, reasoning=runtime_reasoning)

        iteration_override = (
            max_iterations
            if max_iterations is not None
            else (cloud_config or {}).get("max_iterations")
        )
        iteration_cap = self.max_iterations
        if iteration_override is not None:
            try:
                iteration_cap = max(int(iteration_override), 1)
            except (TypeError, ValueError):
                logger.warning(
                    "Invalid iteration override %s, keep default %d",
                    iteration_override,
                    self.max_iterations,
                )
                iteration_cap = self.max_iterations

        original_api_key = self.api_key
        original_base_url = self.base_url
        original_tier = self.provider_models.get(provider_key, base_tier)

        self.api_key = runtime_api_key
        self.base_url = runtime_base_url
        self.provider_models[provider_key] = active_tier

        await cancellation_service.raise_if_cancelled(*cancel_tokens_list)

        logger.info(
            "Starting deep research workflow: provider=%s, general=%s, reasoning=%s, iterations=%d, question=%s",
            provider_key,
            active_tier.general,
            active_tier.reasoning,
            iteration_cap,
            question,
        )

        try:
            initial_decision = await cancellation_service.wait_or_cancel(
                self._judge_complexity(question, provider_key),
                cancel_tokens_list,
            )
            if progress_id:
                progress_service.add_update(
                    progress_id,
                    phase="complexity_decision",
                        title="问题自动分类",
                    message=initial_decision.rationale,
                    data=initial_decision.model_dump(),
                )

            if initial_decision.level == "simple":
                logger.info("Classified as a simple question, delegating to basic logic.")
                simple_result = await cancellation_service.wait_or_cancel(
                    chat_service.get_response(
                        message=question,
                        llm_type=provider_key,
                        enable_rag=False,
                        enable_web_search=False,
                        cancel_tokens=cancel_tokens_list,
                        cloud_config=cloud_config,
                    ),
                    cancel_tokens_list,
                )
                simple_result["meta"] = {
                    "strategy": "simple_fallback",
                    "complexity": initial_decision.model_dump(),
                }
                simple_result["trace"] = {
                    "complexity_decision": initial_decision.model_dump(),
                    "iterations": [],
                }
                if progress_id:
                    progress_service.add_update(
                        progress_id,
                        phase="final_response",
                        title="生成基础回复",
                        message="回复已生成完毕，请查看聊天窗口。",
                        data={"mode": "simple"},
                    )
                    progress_service.finish_progress(
                        progress_id,
                        final_trace=simple_result.get("trace"),
                        final_payload=simple_result,
                    )
                return simple_result

            try:
                deep_result = await cancellation_service.wait_or_cancel(
                    self._iterate_research(
                        question,
                        provider_key,
                        iteration_cap,
                        progress_id=progress_id,
                        cancel_tokens=cancel_tokens_list,
                        library_type=library_type,
                        knowledge_group_ids=knowledge_group_ids,
                        enable_web_search=enable_web_search,
                        enable_rag=enable_rag,
                    ),
                    cancel_tokens_list,
                )
            except OperationCancelledError:
                raise
            except Exception as exc:
                if progress_id:
                    progress_service.mark_error(progress_id, str(exc))
                raise

            meta = deep_result.setdefault("meta", {})
            meta["complexity"] = initial_decision.model_dump()
            meta["strategy"] = meta.get("strategy", "deep_research")

            trace = deep_result.setdefault("trace", {})
            trace["complexity_decision"] = initial_decision.model_dump()
            trace.setdefault("iterations", [])

            return deep_result
        finally:
            self.api_key = original_api_key
            self.base_url = original_base_url
            self.provider_models[provider_key] = original_tier

    def _adjust_plan_by_global_settings(
        self,
        plan: PlanOutput,
        enable_web_search: bool,
        enable_rag: bool
    ) -> PlanOutput:
        """
        根据全局开关修正计划中的任务配置，确保前端显示与实际执行一致

        Args:
            plan: 原始计划
            enable_web_search: 是否启用联网搜索（影响外部工具）
            enable_rag: 是否启用RAG（影响文档检索）

        Returns:
            修正后的计划
        """
        adjusted_tasks = []
        for task in plan.tasks:
            task_dict = task.model_dump()

            # 不勾选联网搜索 → 强制禁用所有外部工具
            if not enable_web_search:
                if task_dict.get('requires_tool'):
                    logger.info(
                        "Adjusting task '%s': disabling tool '%s' due to enable_web_search=False",
                        task_dict.get('task_name'),
                        task_dict.get('tool_name')
                    )
                task_dict['requires_tool'] = False
                task_dict['tool_name'] = None
                task_dict['tool_arguments'] = None

            # 不勾选RAG → 强制禁用文档检索
            if not enable_rag:
                if task_dict.get('requires_vector_search'):
                    logger.info(
                        "Adjusting task '%s': disabling vector search due to enable_rag=False",
                        task_dict.get('task_name')
                    )
                task_dict['requires_vector_search'] = False

            adjusted_tasks.append(PlanTask.model_validate(task_dict))

        return PlanOutput(
            overall_strategy=plan.overall_strategy,
            tasks=adjusted_tasks
        )

    async def _iterate_research(
        self,
        question: str,
        provider_key: str,
        iteration_limit: int,
        progress_id: Optional[str] = None,
        cancel_tokens: Optional[List[str]] = None,
        library_type: Optional[str] = None,
        knowledge_group_ids: Optional[List[str]] = None,
        enable_web_search: bool = False,
        enable_rag: bool = False,
    ) -> Dict[str, Any]:
        cancel_tokens = cancel_tokens or []
        context_summaries: List[str] = []
        reference_chunks: List[Dict[str, Any]] = []
        iterations_trace: List[Dict[str, Any]] = []
        synthesis: Optional[str] = None
        followup_question = question

        for iteration in range(iteration_limit):
            await cancellation_service.raise_if_cancelled(*cancel_tokens)
            plan = await cancellation_service.wait_or_cancel(
                self._plan_tasks(followup_question, provider_key, context_summaries),
                cancel_tokens,
            )

            if progress_id:
                progress_service.add_update(
                    progress_id,
                    phase="plan_generated",
                    title=f"第 {iteration + 1} 轮任务分解",
                    message=plan.overall_strategy,
                    data={
                        "plan": plan.model_dump(),
                        "task_summaries": [task.model_dump() for task in plan.tasks],
                    },
                )

                # 等待用户确认计划
                logger.info("Waiting for user approval of plan for progress_id=%s", progress_id)

                # 根据全局开关修正计划配置，确保编辑窗口显示的计划符合实际约束
                plan_for_approval = self._adjust_plan_by_global_settings(plan, enable_web_search, enable_rag)

                # 创建事件并存储计划（存储修正后的计划）
                approval_event = asyncio.Event()
                self._plan_approval_events[progress_id] = approval_event
                self._pending_plans[progress_id] = {
                    "plan": plan_for_approval,  # 存储修正后的计划
                    "revised_plan": None,
                }

                # 发送等待确认的进度更新（使用修正后的计划）
                progress_service.add_update(
                    progress_id,
                    phase="plan_awaiting_approval",
                    title="计划已生成，等待您的确认",
                    message="请在弹出的窗口中查看并编辑计划，然后点击确认继续执行。",
                    data={
                        "plan": plan_for_approval.model_dump(),
                        "task_summaries": [task.model_dump() for task in plan_for_approval.tasks],
                    },
                )

                # 等待用户确认（带超时，避免无限等待）
                try:
                    # 等待用户确认，最多等待10分钟
                    await asyncio.wait_for(approval_event.wait(), timeout=600)

                    # 获取用户修订的计划
                    revised_plan_data = self._pending_plans[progress_id].get("revised_plan")
                    if revised_plan_data:
                        # 使用用户修订的计划
                        plan = PlanOutput.model_validate(revised_plan_data)
                        logger.info("Using revised plan from user for progress_id=%s", progress_id)

                        # 根据全局开关修正计划配置，确保前端显示与实际执行一致
                        plan = self._adjust_plan_by_global_settings(plan, enable_web_search, enable_rag)

                        # 发送计划已确认的进度更新
                        progress_service.add_update(
                            progress_id,
                            phase="plan_approved",
                            title=f"第 {iteration + 1} 轮执行计划（已确认）",
                            message="正在按照您修订的计划执行任务...",
                            data={
                                "plan": plan.model_dump(),
                                "task_summaries": [task.model_dump() for task in plan.tasks],
                            },
                        )
                    else:
                        logger.warning("No revised plan received for progress_id=%s, using original plan", progress_id)

                except asyncio.TimeoutError:
                    logger.warning("Plan approval timeout for progress_id=%s, using original plan", progress_id)

                    # 根据全局开关修正计划配置
                    plan = self._adjust_plan_by_global_settings(plan, enable_web_search, enable_rag)

                    progress_service.add_update(
                        progress_id,
                        phase="plan_timeout",
                        title=f"第 {iteration + 1} 轮执行计划（等待超时）",
                        message="未在规定时间内收到确认，将使用原始计划继续执行。",
                        data={
                            "plan": plan.model_dump(),
                            "task_summaries": [task.model_dump() for task in plan.tasks],
                        },
                    )
                finally:
                    # 清理
                    if progress_id in self._plan_approval_events:
                        del self._plan_approval_events[progress_id]
                    if progress_id in self._pending_plans:
                        del self._pending_plans[progress_id]

            execution_results, task_references = await cancellation_service.wait_or_cancel(
                self._execute_tasks(
                    question,
                    plan,
                    provider_key,
                    progress_id=progress_id,
                    library_type=library_type,
                    knowledge_group_ids=knowledge_group_ids,
                    enable_web_search=enable_web_search,
                    enable_rag=enable_rag,
                ),
                cancel_tokens,
            )
            reference_chunks.extend(task_references)

            synthesis = await cancellation_service.wait_or_cancel(
                self._synthesize(question, plan, execution_results, provider_key),
                cancel_tokens,
            )

            decision = await cancellation_service.wait_or_cancel(
                self._iteration_guard(
                    question, plan, execution_results, synthesis, provider_key
                ),
                cancel_tokens,
            )

            logger.info(
                "Iteration review result: status=%s, reason=%s", decision.status, decision.reason
            )

            iteration_summary = self._build_iteration_summary(
                plan, execution_results, decision
            )

            iteration_entry = {
                "iteration": iteration + 1,
                "plan": plan.model_dump(),
                "tasks": execution_results,
                "synthesis": synthesis,
                "decision": decision.model_dump(),
                "iteration_summary": iteration_summary,
                "references": [
                    {
                        "source": entry.get("source", "未知来源"),
                        "content": entry.get("content", ""),
                        "score": entry.get("score"),
                        "chunk_index": entry.get("chunk_index"),
                    }
                    for entry in task_references
                ],
            }
            iterations_trace.append(iteration_entry)

            if progress_id:
                progress_service.add_update(
                    progress_id,
                    phase="iteration_decision",
                    title=f"第 {iteration + 1} 轮成果复核与迭代判定",
                    message=decision.reason,
                    data={
                        "decision": decision.model_dump(),
                        "iteration_summary": iteration_summary,
                        "synthesis": synthesis,
                        "iteration_limit_reached": iteration == iteration_limit - 1,
                    },
                )

            if decision.status == "complete" or iteration == iteration_limit - 1:
                final_payload = {
                    "response": synthesis or "",
                    "references": self._format_references(reference_chunks),
                    "meta": {
                        "strategy": "deep_research",
                        "iterations": iteration + 1,
                        "decision": decision.model_dump(),
                        "plan": plan.model_dump(),
                    },
                    "trace": {
                        "iterations": iterations_trace,
                    },
                }
                if progress_id:
                    progress_service.add_update(
                        progress_id,
                        phase="final_response",
                        title="研究完成",
                        message="",
                        data={"iterations": iteration + 1},
                    )
                    progress_service.finish_progress(
                        progress_id,
                        final_trace=final_payload.get("trace"),
                        final_payload=final_payload,
                    )
                return final_payload

            context_summaries.append(iteration_summary)
            followup_question = self._build_followup_question(
                question, decision, context_summaries
            )

            await cancellation_service.raise_if_cancelled(*cancel_tokens)

        final_payload = {
            "response": synthesis or "",
            "references": self._format_references(reference_chunks),
            "meta": {"strategy": "deep_research_fallback"},
            "trace": {
                "iterations": iterations_trace,
            },
        }
        await cancellation_service.raise_if_cancelled(*cancel_tokens)
        if progress_id:
            progress_service.add_update(
                progress_id,
                phase="final_response",
                title="研究完成",
                message=(synthesis or '')[:280],
                data={"iterations": len(iterations_trace)},
            )
            progress_service.finish_progress(
                progress_id,
                final_trace=final_payload.get("trace"),
                final_payload=final_payload,
            )
        return final_payload

    async def _judge_complexity(
        self, question: str, provider_key: str
    ) -> ComplexityDecision:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "你是一个问题分类模型，用于判断用户请求是否需要深入研究。\n"
                        "如果可以直接回答，则返回 'simple'；如果需要规划、检索或复杂推理，则返回 'complex'。\n"
                        "{format_instructions}"
                    ),
                ),
                (
                    "human",
                    (
                        "用户问题：\n{question}\n"
                        "请先用一句话说明你的判断依据，再给出最终类别。使用中文回答。"
                    ),
                ),
            ]
        )

        chain = prompt | self._get_reasoning_model(provider_key, temperature=0.0) | self._complexity_parser
        result = await chain.ainvoke(
            {
                "question": question,
                "format_instructions": self._complexity_parser.get_format_instructions(),
            }
        )
        if isinstance(result, dict):
            return ComplexityDecision.model_validate(result)
        return result

    async def _plan_tasks(
        self, question: str, provider_key: str, context_summaries: List[str]
    ) -> PlanOutput:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "你是一名任务规划助手，需要将复杂问题拆解为 2-5 个有序任务。\n"
                        "需要读取知识库（涵盖少量城市治理研究文档）时，请设置 requires_vector_search=true；若任务需要外部工具，请设置 requires_tool=true，并给出 tool_name 与 tool_arguments。\n"
                        "当前可用的外部工具：\n"
                        "- web_search：使用 API 进行联网搜索，示例参数 {{\"query\": \"...\"}}\n"
                        "- calculator：计算数学表达式，示例参数 {{\"expression\": \"...\"}}\n"
                        "{format_instructions}"
                    ),
                ),
                (
                    "human",
                    (
                        "待解决的核心问题：\n{question}\n"
                        "目前掌握的背景（可能为空）：\n{context_notes}\n"
                        "请输出覆盖信息收集、推理分析和结果综合的任务列表。使用中文回答。"
                    ),
                ),
            ]
        )

        context_notes = "\n".join(f"- {note}" for note in context_summaries) or "目前尚无上下文"

        chain = prompt | self._get_general_model(provider_key, temperature=0.1) | self._plan_parser
        result = await chain.ainvoke(
            {
                "question": question,
                "context_notes": context_notes,
                "format_instructions": self._plan_parser.get_format_instructions(),
            }
        )
        if isinstance(result, dict):
            return PlanOutput.model_validate(result)
        return result

    async def _invoke_tool(self, task: PlanTask) -> Dict[str, Any]:
        tool_name = (task.tool_name or "").strip().lower()
        arguments = task.tool_arguments or {}
        if not tool_name:
            message = "任务被标记为需要工具，但未提供 tool_name。"
            logger.warning(message)
            return {"tool": None, "arguments": arguments, "error": message, "context_snippets": []}

        handler = self._tool_handlers.get(tool_name)
        if handler is None:
            message = f"工具“{tool_name}”暂不支持。"
            logger.warning(message)
            return {"tool": tool_name, "arguments": arguments, "error": message, "context_snippets": []}

        try:
            outcome = handler(task)
            if inspect.isawaitable(outcome):
                outcome = await outcome
        except Exception as exc:  # pragma: no cover - record tool failure
            message = f"调用工具“{tool_name}”失败：{exc}"
            logger.exception(message)
            return {
                "tool": tool_name,
                "arguments": arguments,
                "error": message,
                "context_snippets": [message],
            }

        outcome = outcome or {}
        outcome.setdefault("tool", tool_name)
        outcome.setdefault("arguments", arguments)
        if outcome.get("context_snippets") is None:
            outcome["context_snippets"] = []
        return outcome

    async def _tool_web_search(self, task: PlanTask) -> Dict[str, Any]:
        arguments = task.tool_arguments or {}
        query = str(arguments.get("query") or task.objective or "").strip()
        if not query:
            raise ValueError("web_search 工具需要提供非空的 query 参数。")
        top_k_raw = arguments.get("top_k", 3)
        try:
            top_k = max(1, int(top_k_raw))
        except (TypeError, ValueError):
            top_k = 3

        raw_result = await search_service.search(query)
        organic = raw_result.get("organic") or []
        items = organic[:top_k]
        context_snippets: List[str] = []
        references: List[Dict[str, Any]] = []
        for item in items:
            title = (item.get("title") or "").strip() or "未命名结果"
            snippet = (
                item.get("snippet")
                or item.get("description")
                or item.get("summary")
                or ""
            ).strip()
            url = (item.get("link") or item.get("url") or "").strip()
            summary = f"{title}: {snippet}" if snippet else title
            context_snippets.append(summary)
            references.append(
                {
                    "source": url or title,
                    "content": summary,
                    "type": "web_search",
                }
            )

        if not context_snippets:
            context_snippets.append("未检索到可用的网页结果。")

        return {
            "tool": "web_search",
            "arguments": {"query": query, "top_k": top_k},
            "context_snippets": context_snippets,
            "references": references,
            "raw_result": raw_result,
        }

    async def _tool_calculator(self, task: PlanTask) -> Dict[str, Any]:
        arguments = task.tool_arguments or {}
        expression = str(arguments.get("expression") or task.objective or "").strip()
        if not expression:
            raise ValueError("calculator 工具需要提供 expression 参数。")
        result_value = self._evaluate_math_expression(expression)
        context_snippets = [f"{expression} = {result_value}"]
        return {
            "tool": "calculator",
            "arguments": {"expression": expression},
            "context_snippets": context_snippets,
            "result": result_value,
        }

    def _evaluate_math_expression(self, expression: str) -> float:
        try:
            parsed = ast.parse(expression, mode="eval")
        except SyntaxError as exc:
            raise ValueError(f"无效的表达式“{expression}”：{exc}") from exc
        return float(self._eval_ast_node(parsed.body))

    def _eval_ast_node(self, node: ast.AST) -> float:
        if isinstance(node, ast.BinOp):
            operation = self._math_binary_ops.get(type(node.op))
            if operation is None:
                raise ValueError(f"暂不支持的运算符：{ast.dump(node.op)}")
            left = self._eval_ast_node(node.left)
            right = self._eval_ast_node(node.right)
            return operation(left, right)
        if isinstance(node, ast.UnaryOp):
            operation = self._math_unary_ops.get(type(node.op))
            if operation is None:
                raise ValueError(f"暂不支持的一元运算符：{ast.dump(node.op)}")
            operand = self._eval_ast_node(node.operand)
            return operation(operand)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name):
            if node.id in ("pi", "e"):
                return float(getattr(math, node.id))
            raise ValueError(f"表达式中包含未知标识符“{node.id}”。")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            function = self._math_functions.get(node.func.id)
            if function is None:
                raise ValueError(f"表达式中包含暂不支持的函数“{node.func.id}”。")
            if not node.args or len(node.args) != 1:
                raise ValueError("当前仅支持包含一个参数的数学函数。")
            argument_value = self._eval_ast_node(node.args[0])
            return float(function(argument_value))
        raise ValueError(f"表达式中包含无法解析的结构：{ast.dump(node)}")

    async def _execute_tasks(
        self,
        question: str,
        plan: PlanOutput,
        provider_key: str,
        progress_id: Optional[str] = None,
        library_type: Optional[str] = None,
        knowledge_group_ids: Optional[List[str]] = None,
        enable_web_search: bool = False,
        enable_rag: bool = False,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        results: List[Dict[str, Any]] = []
        references: List[Dict[str, Any]] = []

        for index, task in enumerate(plan.tasks, start=1):
            logger.info("Executing task %d: %s", index, task.task_name)

            # 根据全局开关控制任务能力
            # 创建任务副本以确保修改生效
            task_dict = task.model_dump()

            # 不勾选联网搜索 → 强制禁用工具
            if not enable_web_search:
                if task_dict.get('requires_tool'):
                    logger.info(
                        "Task %d originally required tool '%s', but enable_web_search=False, disabling tool",
                        index,
                        task_dict.get('tool_name')
                    )
                task_dict['requires_tool'] = False
                task_dict['tool_name'] = None
                task_dict['tool_arguments'] = None

            # 不勾选RAG范围 → 强制禁用知识库检索
            if not enable_rag:
                if task_dict.get('requires_vector_search'):
                    logger.info(
                        "Task %d originally required vector search, but enable_rag=False, disabling RAG",
                        index
                    )
                task_dict['requires_vector_search'] = False

            # 从修改后的字典重新创建任务对象
            task = PlanTask.model_validate(task_dict)

            logger.info(
                "Task %d final config: requires_tool=%s, requires_vector_search=%s",
                index,
                task.requires_tool,
                task.requires_vector_search
            )

            vector_context: List[Dict[str, Any]] = []
            vector_status = "未启用文档检索"
            vector_state = "muted"
            vector_chip_text = "未启用"
            if task.requires_vector_search:
                vector_status = "开始检索知识库文档"
                vector_state = "warning"
                vector_chip_text = "检索中"
                try:
                    vector_context = await document_service.search_similar_texts(
                        query=task.objective,
                        k=3, 
                        library_type=library_type,
                        knowledge_group_ids=knowledge_group_ids
                    )
                    references.extend(vector_context)
                    if vector_context:
                        vector_status = f"成功检索到 {len(vector_context)} 条文档片段"
                        vector_state = "success"
                        vector_chip_text = f"命中 {len(vector_context)}"
                    else:
                        vector_status = "文档检索完成，但没有找到相关片段"
                        vector_state = "warning"
                        vector_chip_text = "未命中"
                except Exception as error:
                    logger.error("Vector search failed: %s", error)
                    vector_context = []
                    vector_status = f"文档检索失败：{error}"
                    vector_state = "error"
                    vector_chip_text = "失败"

            tool_output: Optional[Dict[str, Any]] = None
            tool_context_lines: List[str] = []
            tool_status = "未启用外部工具"
            tool_state = "muted"
            tool_chip_text = "未启用"
            if task.requires_tool:
                tool_status = f"准备调用工具 {task.tool_name or '(未指定)'}"
                tool_state = "warning"
                tool_chip_text = "执行中"
                tool_output = await self._invoke_tool(task)
                tool_context_lines = list(tool_output.get("context_snippets") or [])
                tool_references = tool_output.get("references") or []
                if tool_references:
                    references.extend(tool_references)
                if tool_output.get("error"):
                    logger.warning("Tool error for %s: %s", task.task_name, tool_output["error"])
                    tool_status = f"调用工具失败：{tool_output['error']}"
                    tool_state = "error"
                    tool_chip_text = "失败"
                else:
                    tool_name_display = tool_output.get("tool") or (task.tool_name or "工具")
                    tool_status = f"成功调用工具 {tool_name_display}"
                    tool_state = "success"
                    tool_chip_text = f"{tool_name_display} 成功"

            status_chips = [
                {"category": "document", "state": vector_state, "text": vector_chip_text},
                {"category": "tool", "state": tool_state, "text": tool_chip_text},
            ]
            task_prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        (
                            "你需要作为研究助理处理一个更大研究中的子任务。\n"
                            "请谨慎使用任何提供的上下文；如果没有提供，则依靠推理和通用知识。使用中文回答。\n"
                        ),
                    ),
                    (
                        "human",
                        (
                            "原始问题：{question}\n"
                            "当前子任务：{task_description}\n"
                            "目标：{objective}\n"
                            "上下文片段：\n{context_block}\n"
                        ),
                    ),
                ]
            )

            context_sections: List[str] = []
            if vector_context:
                context_lines = [
                    f"- [{entry.get('source', '未知来源')}] {entry.get('content', '')}"
                    for entry in vector_context
                ]
                context_sections.append("向量检索片段：\n" + "\n".join(context_lines))
            if tool_context_lines:
                tool_lines = [f"- {line}" for line in tool_context_lines]
                context_sections.append("工具返回：\n" + "\n".join(tool_lines))
            context_block = "\n\n".join(context_sections) if context_sections else "（暂无外部上下文）"

            model = (
                self._get_general_model(provider_key, temperature=0.2)
                if task.model_preference == "general"
                else self._get_reasoning_model(provider_key, temperature=0.0)
            )
            chain = task_prompt | model | self._str_parser
            execution = await chain.ainvoke(
                {
                    "question": question,
                    "task_description": task.task_name,
                    "objective": task.objective,
                    "context_block": context_block,
                }
            )

            references_snapshot = [
                {
                    "source": entry.get("source", "未知来源"),
                    "content": entry.get("content", ""),
                    "score": entry.get("score"),
                    "chunk_index": entry.get("chunk_index"),
                }
                for entry in vector_context
            ]

            results.append(
                {
                    "task_index": index,
                    "task": task.model_dump(),
                    "output": execution,
                    "references_used": references_snapshot,
                    "tool_output": tool_output,
                    "vector_status": vector_status,
                    "tool_status": tool_status,
                    "status_chips": status_chips,
                }
            )

            if progress_id:
                status_summary = execution
                progress_service.add_update(
                    progress_id,
                    phase="task_completed",
                    title=f"完成子任务 {index}：{task.task_name}",
                    message=status_summary,
                    data={
                        "task": task.model_dump(),
                        "references_used": references_snapshot,
                        "vector_status": vector_status,
                        "tool_status": tool_status,
                        "status_chips": status_chips,
                    },
                )

        return results, references

    async def _synthesize(
        self,
        question: str,
        plan: PlanOutput,
        execution_results: List[Dict[str, Any]],
        provider_key: str,
    ) -> str:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "你将负责整合研究结果。\n"
                        "请根据研究问题、规划概要和任务执行，生成符合要求的结论。使用中文回答。\n"
                    ),
                ),
                (
                    "human",
                    (
                        "研究问题：{question}\n"
                        "规划概要：{strategy}\n"
                        "任务执行：\n{execution_notes}\n"
                    ),
                ),
            ]
        )

        execution_notes = "\n\n".join(
            f"Task {item['task_index']} - {item['task']['task_name']}:\n{item['output']}"
            for item in execution_results
        )

        chain = prompt | self._get_general_model(provider_key, temperature=0.2) | self._str_parser
        return await chain.ainvoke(
            {
                "question": question,
                "strategy": plan.overall_strategy,
                "execution_notes": execution_notes,
            }
        )

    async def _iteration_guard(
        self,
        question: str,
        plan: PlanOutput,
        execution_results: List[Dict[str, Any]],
        synthesis: str,
        provider_key: str,
    ) -> IterationDecision:
        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    (
                        "你需要审核当前结果并决定是否需要进一步研究。\n"
                        "当证据和推理充分时返回 'complete'；否则返回 'iterate' 并说明缺失的内容。使用中文回答。\n"
                        "{format_instructions}"
                    ),
                ),
                (
                    "human",
                    (
                        "原始问题：{question}\n"
                        "计划摘要：{plan_summary}\n"
                        "任务要点：{execution_brief}\n"
                        "当前综合：{synthesis}\n"
                        "我们是否需要继续迭代？\n"
                    ),
                ),
            ]
        )

        execution_brief = "\n".join(
            f"- Task {item['task_index']} {item['task']['task_name']}: completed"
            for item in execution_results
        )

        chain = prompt | self._get_reasoning_model(provider_key, temperature=0.0) | self._iteration_parser
        result = await chain.ainvoke(
            {
                "question": question,
                "plan_summary": plan.overall_strategy,
                "execution_brief": execution_brief,
                "synthesis": synthesis,
                "format_instructions": self._iteration_parser.get_format_instructions(),
            }
        )
        if isinstance(result, dict):
            return IterationDecision.model_validate(result)
        return result

    @staticmethod
    def _format_references(chunks: List[Dict[str, Any]]) -> Optional[List[Dict[str, Any]]]:
        if not chunks:
            return None
        unique_entries: List[Dict[str, Any]] = []
        seen = set()
        for entry in chunks:
            if isinstance(entry, dict):
                content = (entry.get("content") or "").strip()
                source = entry.get("source") or "检索引用"
                ref_type = entry.get("type")
            else:
                content = str(entry).strip()
                source = "检索引用"
                ref_type = None
            if not content:
                continue
            key = (source, content)
            if key in seen:
                continue
            seen.add(key)

            reference = {"title": source, "content": content}
            if ref_type:
                reference["type"] = ref_type
            if ref_type == "web_search":
                reference["url"] = source

            unique_entries.append(reference)
        return unique_entries or None

    @staticmethod
    def _build_iteration_summary(
        plan: PlanOutput, execution_results: List[Dict[str, Any]], decision: IterationDecision
    ) -> str:
        missing = (
            "\n".join(decision.missing_information)
            if decision.missing_information
            else "No additional requirements listed."
        )
        return (
            f"策略概述：{plan.overall_strategy}\n"
            f"已执行任务数：{len(execution_results)}\n"
            f"质量评估：{decision.reason}\n"
            f"待补充要点：{missing}"
        )

    @staticmethod
    def _build_followup_question(
        original_question: str,
        decision: IterationDecision,
        context_summaries: List[str],
    ) -> str:
        notes = "\n".join(context_summaries) or "No summaries yet."
        missing = (
            "\n".join(decision.missing_information)
            if decision.missing_information
            else "Unspecified gaps."
        )
        return (
            f"{original_question}\n"
            f"Current summary:\n{notes}\n"
            f"The review highlighted these gaps:\n{missing}\n"
            "Please continue the research focusing on the missing items."
        )

    def _normalize_provider(self, llm_type: str) -> str:
        value = (llm_type or "deepseek").lower()
        if value not in self.provider_models:
            logger.warning("Unrecognised llm_type=%s, defaulting to deepseek.", llm_type)
            value = "deepseek"
        return value

    def _get_general_model(self, provider_key: str, temperature: float) -> ChatOpenAI:
        tier = self.provider_models.get(provider_key)
        model_name = tier.general if tier else ""
        if not model_name:
            raise ValueError("未配置通用模型名称。")
        return self._build_llm(model_name, temperature)

    def _get_reasoning_model(self, provider_key: str, temperature: float) -> ChatOpenAI:
        tier = self.provider_models.get(provider_key)
        model_name = tier.reasoning if tier else ""
        if not model_name:
            raise ValueError("未配置推理模型名称。")
        return self._build_llm(model_name, temperature)

    def _build_llm(self, model_name: str, temperature: float) -> ChatOpenAI:
        if not self.api_key or not self.base_url:
            raise ValueError("API key or base URL missing for deep research model call.")
        return ChatOpenAI(
            model=model_name,
            temperature=temperature,
            openai_api_key=self.api_key,
            openai_api_base=self.base_url,
        )


deep_research_service = DeepResearchService()







