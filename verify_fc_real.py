"""
改造点1 真实端到端验证（真实 DeepSeek + 真实 Serper）。
知识库模块（faiss/torch）用 mock 顶替，因为本机未装 RAG 依赖，且其检索逻辑本次未改动。
验证：
  1. 纯对话（开关全关）——不调工具
  2. 开联网——模型自主决定是否调用 web_search（真实 Serper）
  3. 开 RAG——模型自主调用 search_knowledge_base（mock 假数据，验证分发与编号）
"""
import asyncio
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

PROJECT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT / ".env", override=True)

# ---- mock 掉重依赖的 document 模块（避免 faiss/torch）----
_doc_mod = types.ModuleType("backend.app.services.document")
_ds = MagicMock()


async def _fake_search_similar_texts(*args, **kwargs):
    return [
        {
            "content": "政策扩散理论（Policy Diffusion）由美国学者提出，指政策创新在不同地区、"
                       "层级政府之间通过学习、竞争、模仿和强制等机制传播的过程。",
            "source": "政策扩散理论研究.pdf",
            "chunk_index": 0,
            "library_type": "public",
        }
    ]


_ds.search_similar_texts = _fake_search_similar_texts
_doc_mod.document_service = _ds
sys.modules["backend.app.services.document"] = _doc_mod

from backend.app.services.chat import chat_service  # noqa: E402


async def main():
    # 1. 纯对话
    print("=" * 70)
    print("【1】纯对话（两个开关都关，普通问候）")
    chat_service.clear_history()
    r = await chat_service.get_response(
        message="你好，请用一句话介绍你自己。",
        llm_type="deepseek",
        enable_rag=False,
        enable_web_search=False,
    )
    print("回答：", r["response"][:150])
    print("引用（应为 None）：", r["references"])

    # 2. 开联网（真实 Serper）
    print("\n" + "=" * 70)
    print("【2】开联网（问时效性问题，应自主调用 web_search）")
    chat_service.clear_history()
    r = await chat_service.get_response(
        message="最近国内有什么数字政府或城市治理相关的新闻？用两三句话简要回答。",
        llm_type="deepseek",
        enable_rag=False,
        enable_web_search=True,
    )
    print("回答：", r["response"][:300])
    print("引用数量：", len(r["references"]) if r["references"] else 0)
    print("citation_map：", r["citation_map"])

    # 3. 开 RAG（mock 知识库，验证工具分发与编号）
    print("\n" + "=" * 70)
    print("【3】开 RAG（问政策扩散理论，应自主调用 search_knowledge_base）")
    chat_service.clear_history()
    r = await chat_service.get_response(
        message="什么是政策扩散理论？",
        llm_type="deepseek",
        enable_rag=True,
        enable_web_search=False,
    )
    print("回答：", r["response"][:300])
    print("引用数量：", len(r["references"]) if r["references"] else 0)
    print("citation_map：", r["citation_map"])


if __name__ == "__main__":
    asyncio.run(main())
