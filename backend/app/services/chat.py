from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict

from backend.app.services.cancellation import OperationCancelledError, cancellation_service
from backend.app.services.document import document_service
from backend.app.services.search import search_service

LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

# 获取项目根目录
ROOT_DIR = Path(__file__).resolve().parents[3]
METADATA_FILE = ROOT_DIR / "backend" / "data" / "metadata.json"


class Message(BaseModel):
    role: str
    content: str
    model_config = ConfigDict(protected_namespaces=())

class ChatService:
    # ================= Function Calling 工具定义（JSON Schema）=================
    # 前端开关在这里充当"授权闸门"：只有开启了对应能力，才会把该工具注册给模型；
    # 一旦注册，是否调用、调用哪个、传什么参数，由模型自主决定（Agent 自主路由）。
    TOOL_DEFINITIONS: Dict[str, Dict[str, Any]] = {
        "search_knowledge_base": {
            "type": "function",
            "function": {
                "name": "search_knowledge_base",
                "description": (
                    "检索城市治理课程知识库，内容包括政策文件、学术论文、治理案例等。"
                    "当用户询问城市治理相关的理论、政策、概念、案例，或需要引用课程资料时使用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "用于语义检索的查询语句，应是与用户问题相关的关键词或短语",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "返回的相关片段数量，默认 3",
                            "default": 3,
                        },
                    },
                    "required": ["query"],
                },
            },
        },
        "web_search": {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": (
                    "联网搜索最新信息、时事新闻、实时数据，或知识库中没有的内容。"
                    "当用户询问近期发生的事件、最新政策、需要时效性信息时使用。"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "搜索关键词，简洁明确",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "返回的搜索结果数量，默认 3",
                            "default": 3,
                        },
                    },
                    "required": ["query"],
                },
            },
        },
    }

    def __init__(self) -> None:
        default_api_key = os.getenv("OPENAI_API_KEY", "")
        default_base_url = os.getenv("OPENAI_BASE_URL", "")
        self.default_api_key = default_api_key
        self.default_base_url = default_base_url
        self.cloud_client = AsyncOpenAI(api_key=default_api_key, base_url=default_base_url)

        self.model_settings: Dict[str, Dict[str, Any]] = {
            "deepseek": {
                "model": os.getenv("GENERAL_MODEL_NAME", "deepseek-chat"),
            },
            "deepseek-reasoner": {
                "model": os.getenv("REASONING_MODEL_NAME", "deepseek-reasoner"),
            },
            "qwen": {
                "model": "qwen-max-latest",
                "api_key": os.getenv("DASHSCOPE_API_KEY", ""),
                "base_url": os.getenv("DASHSCOPE_BASE_URL", ""),
            },
            "gpt": {
                "model": "gpt-4o",
                "api_key": os.getenv("GPT_API_KEY", ""),
                "base_url": os.getenv("GPT_BASE_URL", ""),
            },
            "custom": {"model": "", "supports_web_search": False},
        }
        self.base_system_prompt = (
            "你是山大公管智能体，由山东大学政治学与公共管理学院开发，"
            "专门服务于公共管理学科的教学与研究工作。\n\n"
            "## 你的职责\n"
            "- 解答公共管理学科概念与理论问题\n"
            "- 辅助学术论文的阅读、分析与写作\n"
            "- 分析公共政策案例，提供多维度解读\n"
            "- 推荐相关学术文献与研究前沿\n\n"
            "## 回答规范\n"
            "- 使用 Markdown 格式化输出，确保结构清晰、层次分明\n"
            "- 使用标题（##、###）划分内容板块\n"
            "- 概念解析时使用**加粗**强调关键术语\n"
            "- 如有多个要点，使用有序列表或无序列表呈现\n"
            "- 回答应学术规范、条理清晰、引用有据\n"
            "- 不确定时请如实说明，不要编造\n"
            "- 涉及数据对比时优先使用表格呈现\n\n"
            "## 输出格式红线\n"
            "- **绝对禁止**输出 JSON、XML 或其他纯结构化数据格式\n"
            "- **绝对禁止**使用花括号 {} 包裹内容作为顶层输出\n"
            "- 所有内容必须以自然段落、标题、列表等人类可读的形式呈现\n"
            "- 即便是总结研究趋势、列举热点话题等结构化内容，也必须用段落+列表的形式表述\n"
            "- 你的输出将被直接展示给用户阅读，必须像一篇规范的学术笔记"
        )
        self.base_system_prompt_with_citation = (
            self.base_system_prompt + "\n\n"
            "## 引用规范\n"
            "如果你在回答中使用了【知识库检索结果】中的文献内容，"
            "必须在引用处标注来源编号，格式为[1]、[2]等（对应检索结果中的编号）。"
            "在回答末尾添加【参考文献】段落，列出所有引用的文献标题。"
            "例如：'……政策扩散理论强调……[1][3]。'"
        )
        self._reset_history()

    def _reset_history(self) -> None:
        self.conversation_history: List[Message] = [
            Message(role="system", content=self.base_system_prompt)
        ]

    def _trim_history(self, max_rounds: int = 10) -> None:
        max_messages = 1 + max_rounds * 2
        if len(self.conversation_history) > max_messages:
            self.conversation_history = [
                self.conversation_history[0],
                *self.conversation_history[-(max_messages - 1):],
            ]

    def _resolve_runtime_client(self, cloud_config: Optional[Dict[str, Any]]) -> AsyncOpenAI:
        """
        Build an AsyncOpenAI client using runtime configuration, falling back to the
        default client when no overrides are provided.
        """
        api_key = (cloud_config or {}).get("api_key") or getattr(
            self.cloud_client, "api_key", None
        )
        base_url = (cloud_config or {}).get("base_url") or getattr(
            self.cloud_client, "base_url", None
        )

        if not api_key or not base_url:
            raise ValueError("云端模型缺少 API KEY 或 Base URL，请先完成配置。")

        if (
            api_key == getattr(self.cloud_client, "api_key", None)
            and base_url == getattr(self.cloud_client, "base_url", None)
        ):
            return self.cloud_client

        return AsyncOpenAI(api_key=api_key, base_url=base_url)

    @staticmethod
    def _load_document_metadata(library_type: str = "public") -> Dict[str, Dict[str, Any]]:
        """
        加载文档metadata

        Args:
            library_type: "public" 或 "private"
        """
        if library_type == "public":
            metadata_file = ROOT_DIR / "backend" / "data" / "public" / "metadata.json"
        else:
            metadata_file = ROOT_DIR / "backend" / "data" / "private" / "metadata.json"

        if not metadata_file.exists():
            return {}

        try:
            with open(metadata_file, "r", encoding="utf-8") as file:
                data = json.load(file)

            # 私人库的metadata结构包含knowledge_groups和documents
            if library_type == "private":
                documents = data.get("documents", {})
            else:
                # 公共库的metadata可能是旧格式或新格式
                if isinstance(data, dict) and "documents" in data:
                    documents = data["documents"]
                else:
                    documents = data  # 兼容旧格式

            return documents if isinstance(documents, dict) else {}

        except Exception as exc:  # pragma: no cover - 仅日志
            LOGGER.error("读取 %s metadata.json 失败: %s", library_type, exc)
            return {}

    async def get_response(
        self,
        message: str,
        llm_type: Literal["deepseek", "deepseek-reasoner", "qwen", "gpt", "gemini", "grok", "custom", "local"] = "deepseek",
        enable_rag: bool = False,
        enable_web_search: bool = False,
        cancel_tokens: Optional[List[Optional[str]]] = None,
        cloud_config: Optional[Dict[str, Any]] = None,
        library_type: Optional[str] = None,
        knowledge_group_ids: Optional[List[str]] = None,
        response_format: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        cancel_tokens = [token for token in (cancel_tokens or []) if token]
        try:
            llm_choice = (llm_type or "deepseek").lower()
            if llm_choice == "local":
                LOGGER.warning("微调模型(测试)已禁用，忽略此次请求")
                raise ValueError("微调模型(测试)暂不可用，请选择其他模型。")

            if llm_choice not in self.model_settings:
                LOGGER.warning("未识别的模型类型 %s，默认使用 deepseek", llm_choice)
                llm_choice = "deepseek"

            model_info = self.model_settings[llm_choice]
            override_model = (cloud_config or {}).get("general_model")
            selected_model = override_model or model_info.get("model", "")
            if not selected_model:
                raise ValueError("请提供用于对话的通用模型名称。")

            runtime_config = dict(cloud_config or {})
            if not runtime_config.get("api_key") and model_info.get("api_key"):
                runtime_config["api_key"] = model_info["api_key"]
            if not runtime_config.get("base_url") and model_info.get("base_url"):
                runtime_config["base_url"] = model_info["base_url"]

            client_config = runtime_config if runtime_config else None
            client = self._resolve_runtime_client(client_config)

            await cancellation_service.raise_if_cancelled(*cancel_tokens)

            LOGGER.info(
                "开始处理请求: llm_type=%s, model=%s, enable_web_search=%s",
                llm_choice,
                selected_model,
                enable_web_search,
            )

            # ====== 工具检索：Function Calling 自主路由 ======
            # 前端开关作为"授权闸门"：开启后才把对应能力注册为工具，
            # 由模型自主判断是否调用、调用哪个、调用几次；两个开关都关闭时，
            # 走纯对话路径（行为与原来完全一致）。
            relevant_texts: List[Any] = []
            web_search_results: List[Dict[str, Any]] = []
            citation_map: Dict[int, Dict[str, Any]] = {}

            available_tools: List[Dict[str, Any]] = []
            if enable_rag:
                available_tools.append(self.TOOL_DEFINITIONS["search_knowledge_base"])
            if enable_web_search:
                available_tools.append(self.TOOL_DEFINITIONS["web_search"])

            # 用户原始问题入历史；工具调用的中间过程（tool_calls / tool 消息）
            # 只存在于本轮临时消息中，不写入多轮历史，避免污染上下文。
            self.conversation_history.append(Message(role="user", content=message))

            # 注册了知识库工具时，启用引用规范的 system prompt
            self.conversation_history[0].content = (
                self.base_system_prompt_with_citation
                if enable_rag
                else self.base_system_prompt
            )

            # 本轮发送给模型的完整消息（临时的 tool_calls / tool 消息也在这里）
            api_messages: List[Dict[str, Any]] = [
                {"role": msg.role, "content": msg.content}
                for msg in self.conversation_history
            ]

            response_text = ""

            if not available_tools:
                # 路径 A：未开启任何工具，纯对话（与原逻辑一致）
                request_kwargs: Dict[str, Any] = {
                    "model": selected_model,
                    "messages": api_messages,
                }
                if response_format:
                    request_kwargs["response_format"] = response_format
                completion = await cancellation_service.wait_or_cancel(
                    client.chat.completions.create(**request_kwargs),
                    cancel_tokens,
                )
                response_text = (completion.choices[0].message.content or "").strip()
            else:
                # 路径 B：Function Calling 循环，最多 3 轮工具调用
                for _ in range(3):
                    await cancellation_service.raise_if_cancelled(*cancel_tokens)
                    request_kwargs = {
                        "model": selected_model,
                        "messages": api_messages,
                        "tools": available_tools,
                    }
                    completion = await cancellation_service.wait_or_cancel(
                        client.chat.completions.create(**request_kwargs),
                        cancel_tokens,
                    )
                    assistant_msg = completion.choices[0].message

                    # 模型不再调用工具，给出最终自然语言回答
                    if not assistant_msg.tool_calls:
                        response_text = (assistant_msg.content or "").strip()
                        break

                    # 追加模型的 tool_calls 消息（OpenAI 协议要求原样回传）
                    api_messages.append(assistant_msg.model_dump(exclude_none=True))

                    # 逐个执行工具，并把结果以 tool 角色回传
                    for call in assistant_msg.tool_calls:
                        try:
                            tool_args = json.loads(call.function.arguments or "{}")
                        except (json.JSONDecodeError, TypeError):
                            tool_args = {}
                        LOGGER.info("模型自主调用工具 %s，参数 %s", call.function.name, tool_args)
                        tool_output = await self._execute_chat_tool(
                            func_name=call.function.name,
                            args=tool_args,
                            cancel_tokens=cancel_tokens,
                            library_type=library_type,
                            knowledge_group_ids=knowledge_group_ids,
                            rag_chunks=relevant_texts,
                            web_chunks=web_search_results,
                            citation_map=citation_map,
                        )
                        api_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.id,
                                "content": tool_output,
                            }
                        )
                else:
                    # 达到最大工具轮数仍未收口：去掉 tools 再请求一次，强制模型作答
                    LOGGER.warning("工具调用达到最大轮数，强制收口生成最终回答")
                    await cancellation_service.raise_if_cancelled(*cancel_tokens)
                    completion = await cancellation_service.wait_or_cancel(
                        client.chat.completions.create(
                            model=selected_model,
                            messages=api_messages,
                        ),
                        cancel_tokens,
                    )
                    response_text = (completion.choices[0].message.content or "").strip()

            LOGGER.info("云端模型生成回复完成")
            assistant_message = Message(role="assistant", content=response_text)
            self.conversation_history.append(assistant_message)
            self._trim_history()

            # 合并文档引用和网页搜索结果
            references: Optional[List[Dict[str, Any]]] = None
            all_references: List[Dict[str, Any]] = []

            # 添加文档引用
            if relevant_texts:
                # 加载公共库和私人库的metadata
                public_metadata = self._load_document_metadata("public")
                private_metadata = self._load_document_metadata("private")

                for idx, item in enumerate(relevant_texts):
                    if isinstance(item, dict):
                        filename = item.get("source")
                        snippet = item.get("content", "")
                        chunk_index = item.get("chunk_index")
                        item_library_type = item.get("library_type")
                    else:
                        filename = None
                        snippet = str(item)
                        chunk_index = None
                        item_library_type = "public"

                    # 根据library_type从对应的metadata中获取
                    if item_library_type == "private":
                        meta = private_metadata.get(filename or "", {}) if filename else {}
                    else:
                        meta = public_metadata.get(filename or "", {}) if filename else {}

                    title = meta.get("title") or filename or f"参考资料 {idx + 1}"

                    # 构建reference，包含所有可能的metadata字段
                    reference = {
                        "title": title,
                        "content": snippet,
                        "filename": filename,
                        "category": meta.get("category"),
                        "tags": meta.get("tags"),
                        "size": meta.get("size"),
                        "upload_time": meta.get("upload_time"),
                        "chunk_index": chunk_index,
                        "library_type": item.get("library_type"),
                        "knowledge_group_id": item.get("knowledge_group_id"),
                        "knowledge_group_name": item.get("knowledge_group_name"),
                        "score": item.get("score"),  # 相似度分数
                    }

                    # 添加分类特定字段
                    if meta.get("category") == "政策":
                        reference["effectiveness_level"] = meta.get("effectiveness_level")
                        reference["document_type"] = meta.get("document_type")
                    elif meta.get("category") == "论文":
                        reference["discipline"] = meta.get("discipline")
                        reference["main_topic"] = meta.get("main_topic")
                    elif meta.get("category") == "案例":
                        reference["region"] = meta.get("region")
                        reference["main_topic"] = meta.get("main_topic")

                    all_references.append(reference)

            # 添加网页搜索结果
            if web_search_results:
                all_references.extend(web_search_results)

            if all_references:
                references = all_references

            return {
                "response": response_text,
                "references": references,
                "citation_map": citation_map if citation_map else None,
            }

        except OperationCancelledError:
            if self.conversation_history and self.conversation_history[-1].role == "user":
                self.conversation_history.pop()
            LOGGER.info("对话请求被用户取消")
            raise
        except Exception as exc:
            if self.conversation_history and self.conversation_history[-1].role == "user":
                self.conversation_history.pop()
            LOGGER.error("获取回复失败: %s", exc, exc_info=True)
            raise Exception(f"获取回复失败: {str(exc)}") from exc

    async def _execute_chat_tool(
        self,
        func_name: str,
        args: Dict[str, Any],
        cancel_tokens: List[Optional[str]],
        library_type: Optional[str],
        knowledge_group_ids: Optional[List[str]],
        rag_chunks: List[Any],
        web_chunks: List[Dict[str, Any]],
        citation_map: Dict[int, Dict[str, Any]],
    ) -> str:
        """
        执行 Function Calling 选中的工具，并返回带统一引用编号的文本结果。

        - 检索到的原始片段累积进 rag_chunks / web_chunks，供后续构建 references；
        - 编号信息写入 citation_map，供前端展示引用来源；
        - 知识库片段与网页结果共用一套连续编号 [N]。
        """

        def _next_index() -> int:
            return len(citation_map) + 1

        query = str(args.get("query") or "").strip()
        try:
            top_k = max(1, int(args.get("top_k") or 3))
        except (TypeError, ValueError):
            top_k = 3

        # ---------------- 知识库检索 ----------------
        if func_name == "search_knowledge_base":
            if not query:
                return "检索语句为空，未执行知识库检索。"
            await cancellation_service.raise_if_cancelled(*cancel_tokens)
            try:
                chunks = await cancellation_service.wait_or_cancel(
                    document_service.search_similar_texts(
                        query=query,
                        k=top_k,
                        library_type=library_type,
                        knowledge_group_ids=knowledge_group_ids,
                    ),
                    cancel_tokens,
                )
                chunks = list(chunks or [])[:top_k]
            except Exception as exc:
                LOGGER.error("知识库工具调用失败: %s", exc, exc_info=True)
                return f"知识库检索失败：{exc}"

            if not chunks:
                return "知识库中未检索到与该问题相关的内容。"

            lines = []
            for item in chunks:
                idx = _next_index()
                if isinstance(item, dict):
                    content = item.get("content", "")
                    source = item.get("source", "未知来源")
                else:
                    content = str(item)
                    source = "未知来源"
                rag_chunks.append(item)
                citation_map[idx] = {"source": source, "snippet": content[:300]}
                lines.append(f"[{idx}] 来源：{source}\n{content}")
            return (
                "【知识库检索结果 — 引用编号如下，请在回答中使用 [N] 标注引用来源】\n"
                + "\n\n".join(lines)
            )

        # ---------------- 网页搜索 ----------------
        if func_name == "web_search":
            if not query:
                return "搜索词为空，未执行网页搜索。"
            await cancellation_service.raise_if_cancelled(*cancel_tokens)
            try:
                data = await cancellation_service.wait_or_cancel(
                    search_service.search(query),
                    cancel_tokens,
                )
                items = (data.get("organic") or [])[:top_k]
            except Exception as exc:
                LOGGER.error("网页搜索工具调用失败: %s", exc, exc_info=True)
                return f"网页搜索失败：{exc}"

            if not items:
                return "未检索到可用的网页结果。"

            lines = []
            for item in items:
                idx = _next_index()
                title = (item.get("title") or "").strip() or "未命名结果"
                snippet = (
                    item.get("snippet")
                    or item.get("description")
                    or item.get("summary")
                    or ""
                ).strip()
                url = (item.get("link") or item.get("url") or "").strip()
                summary = f"{title}: {snippet}" if snippet else title
                web_chunks.append(
                    {
                        "title": title,
                        "content": summary,
                        "url": url or title,
                        "type": "web_search",
                    }
                )
                citation_map[idx] = {"source": url or title, "snippet": snippet[:300]}
                lines.append(f"[{idx}] 标题：{title}\n链接：{url}\n摘要：{snippet}")
            return (
                "【网页搜索结果 — 引用编号如下，请在回答中使用 [N] 标注引用来源】\n"
                + "\n\n".join(lines)
            )

        return f"工具 {func_name} 暂不支持。"

    def clear_history(self) -> None:
        self._reset_history()


chat_service = ChatService()
