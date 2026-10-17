import asyncio
import json
import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from openai import AsyncOpenAI

from backend.app.services.cancellation import OperationCancelledError, cancellation_service
from backend.app.services.chat import chat_service
from backend.app.services.knowledge_group import knowledge_group_service

logger = logging.getLogger(__name__)


class Message:
    """简单的消息类，用于对话历史"""
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role, "content": self.content}


class DataAnalysisService:
    """数据分析模式：校验知识组、生成可运行代码、执行并回传结果。支持多轮对话。"""

    def __init__(self) -> None:
        self.default_client: AsyncOpenAI = chat_service.cloud_client
        self.model_settings = chat_service.model_settings
        # 添加对话历史，按知识组ID分组存储
        self.conversation_histories: Dict[str, List[Message]] = {}
        self.max_history_rounds = 10  # 保留最近10轮对话

    def _resolve_client(self, cloud_config: Optional[Dict[str, Any]]) -> AsyncOpenAI:
        # 复用聊天服务的运行时配置解析逻辑
        return chat_service._resolve_runtime_client(cloud_config)  # type: ignore[attr-defined]

    def _get_history_key(self, knowledge_group_id: str) -> str:
        """获取历史记录的key"""
        return knowledge_group_id or "default"

    def _get_history(self, knowledge_group_id: str) -> List[Message]:
        """获取指定知识组的对话历史"""
        key = self._get_history_key(knowledge_group_id)
        if key not in self.conversation_histories:
            # 初始化系统提示
            self.conversation_histories[key] = [
                Message("system",
                    "你是数据分析助手，可以帮助用户分析CSV、Excel、JSON等数据文件。"
                    "你能理解上下文，记住之前的分析结果，并基于历史对话提供连贯的帮助。"
                    "在生成代码时，如果用户提到'刚才的结果'、'之前的分析'等，请参考对话历史。"
                )
            ]
        return self.conversation_histories[key]

    def _add_to_history(self, knowledge_group_id: str, role: str, content: str) -> None:
        """添加消息到历史"""
        history = self._get_history(knowledge_group_id)
        history.append(Message(role, content))
        self._trim_history(knowledge_group_id)

    def _trim_history(self, knowledge_group_id: str) -> None:
        """保留最近的对话历史"""
        history = self._get_history(knowledge_group_id)
        # 保留系统消息 + 最近N轮对话（用户+助手各算一条）
        max_messages = 1 + self.max_history_rounds * 2
        if len(history) > max_messages:
            self.conversation_histories[self._get_history_key(knowledge_group_id)] = [
                history[0],  # 保留系统消息
                *history[-(max_messages - 1):]  # 保留最近的消息
            ]

    def clear_history(self, knowledge_group_id: Optional[str] = None) -> None:
        """清空对话历史"""
        if knowledge_group_id:
            key = self._get_history_key(knowledge_group_id)
            if key in self.conversation_histories:
                del self.conversation_histories[key]
        else:
            # 清空所有历史
            self.conversation_histories.clear()


    def _select_model(
        self,
        llm_type: Optional[str],
        cloud_config: Optional[Dict[str, Any]],
    ) -> str:
        llm_choice = (llm_type or "deepseek").lower()
        if llm_choice not in self.model_settings:
            llm_choice = "deepseek"
        model_info = self.model_settings[llm_choice]
        selected_model = (cloud_config or {}).get("general_model") or model_info.get("model")

        if not selected_model:
            raise ValueError("请提供可用于数据分析的通用模型名称。")
        return selected_model

    @staticmethod
    def _parse_llm_json(raw: str) -> Tuple[str, str, bool]:
        """解析模型返回的JSON，容错处理代码块或普通文本。

        Returns:
            (code, description, needs_code) - needs_code表示是否需要代码
        """
        code = ""
        description = ""
        needs_code = True  # 默认需要代码
        text = raw.strip()

        try:
            payload = json.loads(text)
            code = payload.get("code", "") or ""
            description = payload.get("description", "") or payload.get("summary", "") or payload.get("answer", "") or ""

            # 检查是否直接回答（无需代码）
            if payload.get("needs_code") is False or payload.get("direct_answer") is True:
                needs_code = False
                code = ""  # 清空代码
            elif not code and description:
                # 如果有描述但没有代码，说明是直接回答
                needs_code = False
        except Exception:
            pass

        if not code and not description:
            # 尝试从 Markdown 代码块提取
            if "```" in text:
                segments = text.split("```")
                if len(segments) >= 2:
                    code = segments[1].strip()
                    needs_code = True
            else:
                # 如果没有代码块，可能是直接回答
                description = text
                needs_code = False

        if not description:
            description = text[:200]

        return code.strip(), description.strip(), needs_code

    async def _call_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        client: AsyncOpenAI,
        cancel_tokens: Iterable[Optional[str]],
        use_json_format: bool = True,
        knowledge_group_id: Optional[str] = None,  # 新增：用于获取历史
    ) -> str:
        await cancellation_service.raise_if_cancelled(*cancel_tokens)

        # 如果提供了knowledge_group_id，使用历史记录构建消息
        if knowledge_group_id:
            history = self._get_history(knowledge_group_id)
            messages = [msg.to_dict() for msg in history]
            # 添加当前用户消息
            messages.append({"role": "user", "content": user_prompt})
        else:
            # 不使用历史，单次对话
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]

        # 构建请求参数
        completion_params = {
            "model": model,
            "messages": messages,
        }

        # 只在需要时添加JSON格式要求
        if use_json_format:
            completion_params["response_format"] = {"type": "json_object"}

        completion = await cancellation_service.wait_or_cancel(
            client.chat.completions.create(**completion_params),
            cancel_tokens,
        )
        return completion.choices[0].message.content or ""

    def _build_file_prompt(self, data_files: List[Dict[str, Any]]) -> str:
        lines = []
        for item in data_files:
            lines.append(
                f"- {item.get('filename')} (path: {item.get('file_path')}, type: {item.get('file_type')}, size: {item.get('file_size', 0)} bytes)"
            )
        return "\n".join(lines)

    async def generate_code(
        self,
        instruction: str,
        language: Literal["python", "r"],
        knowledge_group_id: str,
        llm_type: Optional[str],
        cloud_config: Optional[Dict[str, Any]],
        cancel_tokens: Iterable[Optional[str]],
    ) -> Dict[str, Any]:
        try:
            validation = knowledge_group_service.validate_group_for_data_analysis(knowledge_group_id)
            if not validation.get("valid"):
                raise ValueError(validation.get("message") or "所选知识组不可用于数据分析。")

            data_files = validation.get("data_files", [])

            # 构建智能提示词，让AI决定是直接回答还是生成代码
            user_prompt = (
                f"编程语言：{language}\n"
                f"可用数据文件列表（位于同一目录，可直接按文件名读取）：\n{self._build_file_prompt(data_files)}\n\n"
                f"用户指令：{instruction}\n\n"
                "**重要说明**：\n"
                "1. 如果用户的问题可以直接从之前的对话历史中回答（例如询问'刚才的平均值是多少'、'之前的结果是什么'），"
                "请直接回答，不需要生成代码。在这种情况下，返回JSON格式：\n"
                '   {"needs_code": false, "answer": "你的直接回答"}\n\n'
                "2. 如果需要生成新的分析代码，返回JSON格式：\n"
                '   {"needs_code": true, "code": "完整可运行代码", "description": "代码功能描述"}\n\n'
                "代码要求：\n"
                "- 代码需包含数据读取、核心处理和结果打印；如果生成图表，请保存为文件而非展示窗口。\n"
                "- Python优先使用pandas；R优先使用tidyverse；请包含必要的库导入。\n"
                "- **重要**：如果使用matplotlib绘图，必须在代码开头添加中文字体配置，避免中文乱码：\n"
                "  ```python\n"
                "  import matplotlib.pyplot as plt\n"
                "  plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'Arial Unicode MS']\n"
                "  plt.rcParams['axes.unicode_minus'] = False\n"
                "  ```\n"
                "- 路径请直接使用文件名或相对路径，假设当前工作目录即为数据文件所在目录。\n"
                "- 确保输出通过print/console展示核心结果摘要。"
            )

            client = self._resolve_client(cloud_config)
            model = self._select_model(llm_type, cloud_config)

            # 添加用户请求到历史
            self._add_to_history(knowledge_group_id, "user", instruction)

            # 调用LLM，传入knowledge_group_id以使用历史
            raw = await self._call_llm(
                "",  # system_prompt在历史中已有
                user_prompt,
                model,
                client,
                cancel_tokens,
                use_json_format=True,
                knowledge_group_id=knowledge_group_id
            )

            code, description, needs_code = self._parse_llm_json(raw)

            # 如果不需要代码，直接返回答案
            if not needs_code:
                # 将助手回复添加到历史
                self._add_to_history(knowledge_group_id, "assistant", description)

                return {
                    "response": description,
                    "analysis": None,  # 不返回analysis字段
                }

            # 需要代码，正常处理
            if not code:
                raise ValueError("未能生成可运行的代码，请重试或调整指令。")

            # 将助手回复添加到历史
            assistant_message = f"已生成{language}代码。描述：{description}"
            self._add_to_history(knowledge_group_id, "assistant", assistant_message)

            return {
                "response": description or "已生成可运行的分析代码。",
                "analysis": {
                    "action": "generate",
                    "language": language,
                    "code": code,
                    "description": description,
                    "data_files": data_files,
                    "knowledge_group_id": knowledge_group_id,
                },
            }
        except ValueError:
            raise
        except Exception as exc:
            error_msg = str(exc) or "生成代码时发生未知错误"
            logger.error(f"生成代码异常: {error_msg}", exc_info=True)
            raise ValueError(f"生成代码失败: {error_msg}") from exc

    @staticmethod
    def _filter_stderr(stderr: str) -> str:
        """过滤掉无害的警告信息，只保留真正的错误"""
        if not stderr:
            return ""

        lines = stderr.splitlines()
        filtered_lines = []

        # 需要过滤的无害警告关键词
        harmless_warnings = [
            "UserWarning: Glyph",  # matplotlib字体警告
            "missing from current font",
            "findfont:",
            "DeprecationWarning",
            "FutureWarning",
        ]

        for line in lines:
            # 检查是否是无害警告
            is_harmless = any(keyword in line for keyword in harmless_warnings)
            if not is_harmless:
                filtered_lines.append(line)

        return "\n".join(filtered_lines).strip()

    async def _execute_script(
        self,
        language: Literal["python", "r"],
        code: str,
        workdir: Path,
        cancel_tokens: Iterable[Optional[str]],
    ) -> Dict[str, Any]:
        workdir.mkdir(parents=True, exist_ok=True)

        # 记录运行前的图片文件及其修改时间（用于检测新生成或更新的图片）
        image_extensions = {".png", ".jpg", ".jpeg", ".svg", ".pdf", ".gif"}
        existing_files = {}  # 改为字典，存储文件名和修改时间
        if workdir.exists():
            for f in workdir.iterdir():
                if f.is_file() and f.suffix.lower() in image_extensions:
                    existing_files[f.name] = f.stat().st_mtime

        suffix = ".py" if language == "python" else ".r"
        tmp_file = tempfile.NamedTemporaryFile(mode="w", suffix=suffix, delete=False, dir=workdir, encoding="utf-8")
        tmp_file.write(code)
        tmp_file.flush()
        tmp_file.close()

        cmd: List[str]
        if language == "python":
            # 使用多个标志完全隔离环境
            # -u: 无缓冲输出
            # -B: 不生成 .pyc 文件
            # -s: 不添加用户 site-packages
            # -E: 忽略所有 PYTHON* 环境变量
            cmd = [sys.executable, "-u", "-B", "-s", "-E", tmp_file.name]
        else:
            rscript = shutil.which("Rscript")
            if not rscript:
                os.unlink(tmp_file.name)
                raise ValueError("当前环境未安装R/Rscript，无法运行R代码。")
            cmd = [rscript, tmp_file.name]

        try:
            # Windows 系统上使用同步subprocess，避免asyncio事件循环问题
            import platform
            if platform.system() == "Windows":
                # 在 Windows 上使用同步方式执行
                import subprocess

                await cancellation_service.raise_if_cancelled(*cancel_tokens)

                # 创建干净的环境变量，避免继承可能导致问题的变量
                clean_env = os.environ.copy()
                # 移除所有可能导致 multiprocessing 和模块导入问题的环境变量
                for key in ['PYTHONPATH', 'PYTHONSTARTUP', 'PYTHONHOME', '__PYVENV_LAUNCHER__']:
                    clean_env.pop(key, None)

                # 确保子进程不会尝试导入主模块
                clean_env['PYTHONDONTWRITEBYTECODE'] = '1'

                # 使用 run_in_executor 在线程池中运行同步subprocess
                loop = asyncio.get_event_loop()
                process_result = await loop.run_in_executor(
                    None,
                    lambda: subprocess.run(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        cwd=str(workdir),
                        timeout=300,  # 5分钟超时
                        env=clean_env,
                        creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
                        # 完全分离进程，避免继承父进程状态
                        close_fds=False,  # Windows 上必须为 False
                    )
                )

                # Windows上优先尝试gbk编码，失败则用utf-8
                try:
                    stdout_text = process_result.stdout.decode("gbk")
                except (UnicodeDecodeError, AttributeError):
                    stdout_text = process_result.stdout.decode("utf-8", errors="replace")

                try:
                    stderr_text = process_result.stderr.decode("gbk")
                except (UnicodeDecodeError, AttributeError):
                    stderr_text = process_result.stderr.decode("utf-8", errors="replace")

                # 过滤掉无害的警告
                filtered_stderr = self._filter_stderr(stderr_text)

                # 检测新生成或更新的图片文件
                generated_images = []
                if workdir.exists():
                    for f in workdir.iterdir():
                        if f.is_file() and f.suffix.lower() in image_extensions:
                            # 如果是新文件，或者文件被修改过（时间戳不同），都算作生成的图片
                            current_mtime = f.stat().st_mtime
                            if f.name not in existing_files or existing_files[f.name] != current_mtime:
                                generated_images.append({
                                    "filename": f.name,
                                    "path": str(f),
                                    "size": f.stat().st_size
                                })

                return {
                    "stdout": stdout_text,
                    "stderr": filtered_stderr,
                    "exit_code": process_result.returncode,
                    "generated_images": generated_images,
                }
            else:
                # 非Windows系统使用异步方式
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    cwd=str(workdir),
                )

                try:
                    stdout, stderr = await cancellation_service.wait_or_cancel(process.communicate(), cancel_tokens)
                except OperationCancelledError:
                    process.kill()
                    raise

                # 解码并过滤stderr
                stdout_text = stdout.decode("utf-8", errors="ignore")
                stderr_text = stderr.decode("utf-8", errors="ignore")
                filtered_stderr = self._filter_stderr(stderr_text)

                # 检测新生成或更新的图片文件
                generated_images = []
                if workdir.exists():
                    for f in workdir.iterdir():
                        if f.is_file() and f.suffix.lower() in image_extensions:
                            # 如果是新文件，或者文件被修改过（时间戳不同），都算作生成的图片
                            current_mtime = f.stat().st_mtime
                            if f.name not in existing_files or existing_files[f.name] != current_mtime:
                                generated_images.append({
                                    "filename": f.name,
                                    "path": str(f),
                                    "size": f.stat().st_size
                                })

                return {
                    "stdout": stdout_text,
                    "stderr": filtered_stderr,
                    "exit_code": process.returncode,
                    "generated_images": generated_images,
                }
        except subprocess.TimeoutExpired:
            raise ValueError("代码执行超时（超过5分钟），请优化代码或减少数据量")
        except Exception as exc:
            logger.error(f"执行脚本异常: {exc}", exc_info=True)
            raise
        finally:
            try:
                os.unlink(tmp_file.name)
            except OSError:
                logger.warning("清理临时脚本失败: %s", tmp_file.name)

    @staticmethod
    def _summarize_run_result(result: Dict[str, Any]) -> str:
        exit_code = result.get("exit_code")
        stdout = (result.get("stdout") or "").strip()
        stderr = (result.get("stderr") or "").strip()
        parts = []
        if exit_code is not None:
            parts.append(f"退出码: {exit_code}")
        if stdout:
            preview = stdout.splitlines()
            preview_text = "\\n".join(preview[:4])
            parts.append(f"输出预览: {preview_text[:240]}")
        if stderr:
            err_preview = stderr.splitlines()
            parts.append(f"错误提示: {'; '.join(err_preview[:2])[:180]}")
        if not parts:
            return "运行完成，但无输出。"
        return "；".join(parts)

    async def run_code(
        self,
        instruction: str,
        language: Literal["python", "r"],
        knowledge_group_id: str,
        code: str,
        llm_type: Optional[str],
        cloud_config: Optional[Dict[str, Any]],
        cancel_tokens: Iterable[Optional[str]],
    ) -> Dict[str, Any]:
        try:
            validation = knowledge_group_service.validate_group_for_data_analysis(knowledge_group_id)
            if not validation.get("valid"):
                raise ValueError(validation.get("message") or "所选知识组不可用于数据分析。")
            if not code.strip():
                raise ValueError("运行代码时必须提供有效的code内容。")

            group = knowledge_group_service.get_group(knowledge_group_id)
            if not group:
                raise ValueError("知识组不存在或已被删除。")

            # 添加运行请求到历史（如果instruction不是默认的"运行代码"）
            if instruction and instruction != "运行数据分析代码":
                self._add_to_history(knowledge_group_id, "user", instruction)

            workdir = Path(group["storage_path"])
            result = await self._execute_script(language, code, workdir, cancel_tokens)

            # 检查执行结果
            if result.get("exit_code") != 0:
                stderr = result.get("stderr", "").strip()
                stdout = result.get("stdout", "").strip()
                error_msg = stderr or stdout or "代码执行失败，未返回错误信息"
                logger.error(f"代码执行失败: exit_code={result.get('exit_code')}, stderr={stderr}, stdout={stdout}")
                raise ValueError(f"代码执行失败: {error_msg}")

            summary = self._summarize_run_result(result)

            # 调用LLM解释运行结果
            interpretation = ""
            try:
                client = self._resolve_client(cloud_config)
                model = self._select_model(llm_type, cloud_config)

                stdout_text = result.get("stdout", "").strip()
                stderr_text = result.get("stderr", "").strip()

                interpret_system = (
                    "你是数据分析结果解释助手。请用简洁的中文解释代码运行结果的含义，"
                    "包括关键发现、数据特征、统计结果等。避免重复输出内容本身，专注于解释和洞察。"
                )
                interpret_user = (
                    f"用户指令：{instruction}\n\n"
                    f"执行的{language}代码：\n```{language}\n{code}\n```\n\n"
                    f"运行输出：\n{stdout_text[:1000]}\n\n"
                    "请用2-3句话解释这个运行结果的含义和主要发现。直接返回解释文本，不需要JSON格式。"
                )

                # 不使用JSON格式，直接获取文本解释
                interpretation = await self._call_llm(
                    interpret_system,
                    interpret_user,
                    model,
                    client,
                    cancel_tokens,
                    use_json_format=False  # 不要求JSON格式
                )
                interpretation = interpretation.strip()

            except Exception as exc:
                logger.warning(f"生成结果解释失败: {exc}")
                interpretation = ""  # 解释失败不影响主流程

            # 将运行结果添加到历史
            run_summary = interpretation or summary
            self._add_to_history(knowledge_group_id, "assistant", f"代码运行成功。{run_summary}")

            return {
                "response": interpretation or summary,
                "analysis": {
                    "action": "run",
                    "language": language,
                    "code": code,
                    "data_files": validation.get("data_files", []),
                    "description": summary,
                    "run_result": {
                        **result,
                        "summary": summary,
                        "interpretation": interpretation,
                    },
                    "instruction": instruction,
                    "knowledge_group_id": knowledge_group_id,
                },
            }
        except ValueError:
            raise
        except Exception as exc:
            error_msg = str(exc) or "运行代码时发生未知错误"
            logger.error(f"运行代码异常: {error_msg}", exc_info=True)
            raise ValueError(f"运行代码失败: {error_msg}") from exc

    async def handle_request(
        self,
        instruction: str,
        language: Optional[Literal["python", "r"]],
        knowledge_group_id: Optional[str],
        action: Literal["generate", "run"] = "generate",
        code: Optional[str] = None,
        llm_type: Optional[str] = None,
        cloud_config: Optional[Dict[str, Any]] = None,
        cancel_tokens: Optional[Iterable[Optional[str]]] = None,
    ) -> Dict[str, Any]:
        if not language:
            raise ValueError("数据分析模式需要指定编程语言（python或r）。")
        if not knowledge_group_id:
            raise ValueError("数据分析模式需要指定私人知识组。")

        tokens = list(cancel_tokens or [])

        if action == "run":
            return await self.run_code(
                instruction=instruction,
                language=language,
                knowledge_group_id=knowledge_group_id,
                code=code or "",
                llm_type=llm_type,
                cloud_config=cloud_config,
                cancel_tokens=tokens,
            )

        return await self.generate_code(
            instruction=instruction,
            language=language,
            knowledge_group_id=knowledge_group_id,
            llm_type=llm_type,
            cloud_config=cloud_config,
            cancel_tokens=tokens,
        )


data_analysis_service = DataAnalysisService()
