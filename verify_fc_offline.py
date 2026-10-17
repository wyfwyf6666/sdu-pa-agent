"""
离线验证改造后的 chat.py Function Calling 控制流（不连真实 API、不加载 faiss）。
通过 mock 模型响应序列与检索服务，验证：
  场景 A：两个开关都关 -> 纯对话，不调任何工具，references 为 None
  场景 B：开联网 -> 模型先返回 tool_call -> 执行搜索 -> 回传 -> 最终回答，引用编号正确
"""
import asyncio
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

# 提供占位配置，使模块级 ChatService() 可实例化（client 随后会被 mock 替换）
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key")
os.environ.setdefault("OPENAI_BASE_URL", "https://fake.example.com/v1")

# ---- 在 import chat 前，用 mock 顶替重依赖的 document / search 模块 ----
_doc_mod = types.ModuleType("backend.app.services.document")
_doc_service = MagicMock()
_doc_service.search_similar_texts = MagicMock()
_doc_mod.document_service = _doc_service
sys.modules["backend.app.services.document"] = _doc_mod

_search_mod = types.ModuleType("backend.app.services.search")
_search_service = MagicMock()
_search_service.search = MagicMock()
_search_mod.search_service = _search_service
sys.modules["backend.app.services.search"] = _search_mod

from backend.app.services.chat import ChatService  # noqa: E402


# ---------------- 构造 OpenAI 风格的假响应对象 ----------------
class _Func:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, cid, name, arguments):
        self.id = cid
        self.type = "function"
        self.function = _Func(name, arguments)


class _Message:
    def __init__(self, content=None, tool_calls=None):
        self.role = "assistant"
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none=False):
        d: dict = {"role": "assistant"}
        if self.content is not None:
            d["content"] = self.content
        if self.tool_calls is not None:
            d["tool_calls"] = [
                {
                    "id": c.id,
                    "type": "function",
                    "function": {"name": c.function.name, "arguments": c.function.arguments},
                }
                for c in self.tool_calls
            ]
        if exclude_none:
            d = {k: v for k, v in d.items() if v is not None}
        return d


class _Choice:
    def __init__(self, message):
        self.message = message


class _Completion:
    def __init__(self, message):
        self.choices = [_Choice(message)]


class _ScriptedCreate:
    """按预设顺序返回响应的假 create，并记录每次请求参数"""
    def __init__(self, scripted_messages):
        self._scripted = list(scripted_messages)
        self.requests = []

    async def __call__(self, **kwargs):
        self.requests.append(kwargs)
        return _Completion(self._scripted.pop(0))


def make_service(scripted_messages):
    svc = ChatService()
    fake_client = MagicMock()
    fake_client.chat.completions.create = _ScriptedCreate(scripted_messages)
    svc._resolve_runtime_client = lambda cfg: fake_client
    return svc, fake_client


async def test_path_a():
    print("=" * 70)
    print("场景 A：两个开关都关（纯对话）")
    svc, client = make_service([_Message(content="你好，我是城市治理研究助手。")])
    result = await svc.get_response(
        message="你好", llm_type="deepseek", enable_rag=False, enable_web_search=False
    )
    create = client.chat.completions.create
    assert len(create.requests) == 1, "纯对话应只请求 1 次"
    assert "tools" not in create.requests[0], "未开启工具时不应传 tools"
    assert result["references"] is None, "纯对话 references 应为 None"
    assert "你好" in result["response"]
    print("  回答：", result["response"])
    print("  是否传 tools：", "tools" in create.requests[0])
    print("  引用：", result["references"])
    print("  ✓ 通过\n")


async def test_path_b():
    print("=" * 70)
    print("场景 B：开联网，模型自主调用 web_search 后作答")

    # 让 search_service.search 返回一个异步结果
    async def _fake_search(query):
        return {"organic": [
            {"title": "数字政府建设提速", "snippet": "多地推进数字政府改革。", "link": "https://news.example.com/1"}
        ]}
    _search_service.search = _fake_search

    # 模型第 1 次：要求调用 web_search；第 2 次：给出最终回答
    first = _Message(
        tool_calls=[_ToolCall("call_1", "web_search", '{"query": "数字政府 最新新闻"}')]
    )
    second = _Message(content="根据检索，多地正在推进数字政府改革[1]。")
    svc, client = make_service([first, second])

    result = await svc.get_response(
        message="最近有数字政府的新闻吗？",
        llm_type="deepseek",
        enable_rag=False,
        enable_web_search=True,
    )
    create = client.chat.completions.create

    assert len(create.requests) == 2, "应请求 2 次（工具调用 + 最终回答）"
    assert create.requests[0].get("tools"), "第 1 次请求应带 tools"
    assert result["references"] is not None and len(result["references"]) == 1, "应有 1 条引用"
    assert result["citation_map"] and 1 in result["citation_map"], "citation_map 应含编号 [1]"
    # 第二次请求应包含 tool 角色消息
    roles = [m.get("role") for m in create.requests[1]["messages"]]
    assert "tool" in roles, "第二次请求应回传 tool 结果"

    print("  模型请求次数：", len(create.requests))
    print("  第 1 次带 tools：", bool(create.requests[0].get("tools")))
    print("  第 2 次消息角色序列：", roles)
    print("  最终回答：", result["response"])
    print("  引用数：", len(result["references"]))
    print("  引用[0]：", result["references"][0])
    print("  citation_map：", result["citation_map"])
    print("  ✓ 通过\n")


async def main():
    await test_path_a()
    await test_path_b()
    print("全部离线测试通过 ✓")


if __name__ == "__main__":
    asyncio.run(main())
