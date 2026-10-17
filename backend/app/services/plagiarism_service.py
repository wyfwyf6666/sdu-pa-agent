"""开放来源相似度检测服务

对论文正文进行分块、本地知识库比对、网络片段比对，输出综合相似度评分。
不替代知网/维普/万方/Turnitin 等正式查重系统。
"""

from __future__ import annotations

import logging
import os
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

LOGGER = logging.getLogger(__name__)

# 规范化专用正则
_NORM_RE = [
    (re.compile(r"\s+"), " "),  # 多余空白
    (re.compile(r"［"), "["),
    (re.compile(r"］"), "]"),
    (re.compile(r"（"), "("),
    (re.compile(r"）"), ")"),
    (re.compile(r"，"), ","),
    (re.compile(r"。"), "."),
    (re.compile(r"；"), ";"),
    (re.compile(r"："), ":"),
    (re.compile(r"！"), "!"),
    (re.compile(r"？"), "?"),
    (re.compile(r"＂"), '"'),
    (re.compile(r"＇"), "'"),
    (re.compile(r"０-９"), "0-9"),
]


def normalize_text(text: str) -> str:
    """标准化文本：统一全半角、空格、大小写"""
    text = text.strip()
    for pat, repl in _NORM_RE:
        text = pat.sub(repl, text)
    return text.lower()


def _char_is_cjk(c: str) -> bool:
    return "一" <= c <= "鿿" or "㐀" <= c <= "䶿"


def _count_words(text: str) -> int:
    """中文字数 + 英文单词数"""
    chinese = sum(1 for c in text if _char_is_cjk(c))
    english_words = len(re.findall(r"[a-zA-Z]+", text))
    return chinese + english_words


def _is_noise_sentence(text: str) -> bool:
    """判断是否为模板化或无意义的句子，这类句子应跳过"""
    t = text.strip()
    if len(t) < 10:
        return True
    noise_patterns = [
        r"^表\s*\d+", r"^图\s*\d+", r"^Figure\s*\d+", r"^Table\s*\d+",
        r"^参考文献", r"^References", r"^Bibliography",
        r"^[\[\(（]\d+[\]\)）]",  # 纯编号行
        r"^第[一二三四五六七八九十\d]+章", r"^第[一二三四五六七八九十\d]+节",
        r"^本研究获", r"^基金项目", r"^作者简介", r"^收稿日期",
        r"^致\s*谢", r"^Acknowledg",
    ]
    for pat in noise_patterns:
        if re.match(pat, t):
            return True
    # 太短的句子
    if _count_words(t) < 8:
        return True
    return False


def remove_noise_sections(text: str) -> str:
    """去除封面、目录、致谢、参考文献等对查重干扰较大的部分"""
    lines = text.split("\n")
    result_lines: List[str] = []
    skip = False
    skip_patterns = [
        r"^参考文献\s*$", r"^References\s*$", r"^Bibliography\s*$",
        r"^致\s*谢\s*$", r"^Acknowledgements?\s*$",
        r"^附录", r"^Appendix",
    ]
    for line in lines:
        for pat in skip_patterns:
            if re.match(pat, line.strip()):
                skip = True
                break
        if skip:
            continue
        result_lines.append(line)
    return "\n".join(result_lines)


def chunk_text(text: str, min_chars: int = 120, max_chars: int = 300) -> List[Dict[str, Any]]:
    """将文本按句子+段落分块，每块记录位置

    Returns:
        List of {"text": str, "start_char": int, "end_char": int}
    """
    # 按句号、换行分段
    sentences = re.split(r"(?<=[。！？.!?\n])", text)
    chunks: List[Dict[str, Any]] = []
    current = ""
    current_start = 0
    pos = 0

    for sent in sentences:
        if not sent.strip():
            pos += len(sent)
            continue
        if _is_noise_sentence(sent):
            pos += len(sent)
            continue

        if not current:
            current_start = pos
            current = sent
        elif _count_words(current + sent) <= max_chars:
            current += sent
        else:
            if _count_words(current) >= min_chars:
                chunks.append({
                    "text": current.strip(),
                    "start_char": current_start,
                    "end_char": current_start + len(current),
                })
            current = sent
            current_start = pos
        pos += len(sent)

    if current and _count_words(current) >= min_chars:
        chunks.append({
            "text": current.strip(),
            "start_char": current_start,
            "end_char": current_start + len(current),
        })
    return chunks


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """余弦相似度"""
    if a is None or b is None or len(a) == 0 or len(b) == 0:
        return 0.0
    dot = float(np.dot(a, b))
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb)))


def ngram_jaccard(text1: str, text2: str, n: int = 3) -> float:
    """n-gram Jaccard 相似度"""
    def _ngrams(s: str, n: int) -> set:
        s = s.lower()
        return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}
    g1 = _ngrams(text1, n)
    g2 = _ngrams(text2, n)
    if not g1 or not g2:
        return 0.0
    return len(g1 & g2) / len(g1 | g2)


def sequence_similarity(text1: str, text2: str) -> float:
    """SequenceMatcher 相似度"""
    if not text1 or not text2:
        return 0.0
    return SequenceMatcher(None, text1, text2).ratio()


def compute_comprehensive_similarity(
    chunk_text_val: str,
    candidate_text: str,
    embedding_score: float = 0.0,
) -> float:
    """综合计算文本相似度

    权重：
    - n-gram Jaccard (n=3): 0.35
    - SequenceMatcher: 0.35
    - embedding cosine (如果有): 0.30
    """
    jaccard = ngram_jaccard(chunk_text_val, candidate_text)
    seq = sequence_similarity(chunk_text_val, candidate_text)
    if embedding_score > 0:
        return 0.30 * embedding_score + 0.35 * jaccard + 0.35 * seq
    else:
        return 0.5 * jaccard + 0.5 * seq


def select_representative_query(text: str, max_len: int = 40) -> str:
    """从文本中抽取最有代表性的 20-40 字作为搜索 query"""
    # 简单策略：取中间部分，因为首尾可能含过渡词
    chars = list(text)
    if len(chars) <= max_len:
        return text
    mid = len(chars) // 2
    start = max(0, mid - max_len // 2)
    return "".join(chars[start:start + max_len])


def _convert_l2_to_cosine(l2_distance: float) -> float:
    """将 L2 距离近似转换为余弦相似度 (0-1)"""
    # 经验映射：L2=0 -> cosine≈1.0, L2=2 -> cosine≈0.0, L2越高余弦越低
    return max(0.0, min(1.0, 1.0 - l2_distance / 2.0))


class PlagiarismService:
    """开放来源相似度检测服务"""

    def __init__(self):
        self.serper_api_key = os.getenv("SERPER_API_KEY", "")

    def detect_plagiarism(
        self,
        text: str,
        use_web_search: bool = True,
        use_local_kb: bool = True,
        max_web_queries: int = 30,
    ) -> Dict[str, Any]:
        """执行完整的相似度检测

        Args:
            text: 论文全文
            use_web_search: 是否使用网络搜索
            use_local_kb: 是否使用本地知识库
            max_web_queries: 最大网络搜索查询数
        """
        # 1. 预处理
        cleaned_text = remove_noise_sections(text)
        chunks = chunk_text(cleaned_text)

        # 智能筛选：取最重要的 chunk 进行联网搜索（跳过相似度太低的）
        if len(chunks) > max_web_queries and use_web_search:
            # 按文本长度排序，优先搜长的（信息量更大）
            chunks_for_web = sorted(
                chunks, key=lambda c: _count_words(c["text"]), reverse=True
            )[:max_web_queries]
        else:
            chunks_for_web = chunks

        segments: List[Dict[str, Any]] = []
        total_weighted_similarity = 0.0
        total_weight = 0.0
        local_sim_sum = 0.0
        web_sim_sum = 0.0
        local_count = 0
        web_count = 0

        for i, chunk in enumerate(chunks):
            weight = _count_words(chunk["text"])
            matched_sources: List[Dict[str, Any]] = []
            max_local_sim = 0.0
            max_web_sim = 0.0

            # 2. 本地知识库检测
            if use_local_kb:
                try:
                    from backend.app.services.document import document_service as ds
                    import asyncio
                    loop = asyncio.new_event_loop()
                    try:
                        similar_docs = loop.run_until_complete(
                            ds.search_similar_texts(
                                query=chunk["text"], k=3, library_type="public"
                            )
                        )
                    finally:
                        loop.close()
                except Exception as e:
                    LOGGER.warning("Local KB search failed: %s", e)
                    similar_docs = []

                for doc in similar_docs:
                    doc_content = doc.get("content", "")
                    if not doc_content.strip():
                        continue
                    sim = compute_comprehensive_similarity(
                        chunk["text"], doc_content,
                        embedding_score=_convert_l2_to_cosine(
                            doc.get("score", 1.0)
                        ),
                    )
                    if sim > max_local_sim:
                        max_local_sim = sim
                    if sim > 0.3:
                        matched_sources.append({
                            "title": doc.get("source", "本地知识库"),
                            "url": "",
                            "source_type": "local_knowledge_base",
                            "similarity": round(sim, 3),
                            "snippet": doc_content[:200],
                        })

            if max_local_sim > 0:
                local_sim_sum += max_local_sim
                local_count += 1

            # 3. 开放网络检测（每个 chunk 只发一次搜索请求，同时得到相似度与来源，避免重复查询）
            if use_web_search and self.serper_api_key and chunk in chunks_for_web:
                web_results = self._search_web_for_chunk(chunk["text"])
                web_sim = 0.0
                for wr in web_results:
                    wr["source_type"] = "web"
                    matched_sources.append(wr)
                    web_sim = max(web_sim, wr.get("similarity", 0))
                if web_sim > max_web_sim:
                    max_web_sim = web_sim
                if web_sim > 0:
                    web_sim_sum += web_sim
                    web_count += 1

            # 限制匹配来源数
            matched_sources.sort(key=lambda x: x["similarity"], reverse=True)
            matched_sources = matched_sources[:3]

            segment_sim = max(max_local_sim, max_web_sim)
            risk = _similarity_to_risk(segment_sim)

            total_weighted_similarity += segment_sim * weight
            total_weight += weight

            if segment_sim > 0.15:
                segments.append({
                    "index": i + 1,
                    "text": chunk["text"][:300],
                    "start_char": chunk["start_char"],
                    "end_char": chunk["end_char"],
                    "similarity_score": round(segment_sim, 3),
                    "risk_level": risk,
                    "matched_sources": matched_sources,
                    "reason": _build_reason(segment_sim, matched_sources),
                    "suggestion": _build_suggestion(segment_sim),
                })

        total_similarity = (
            total_weighted_similarity / total_weight if total_weight > 0 else 0.0
        )
        local_similarity = local_sim_sum / max(local_count, 1)
        web_similarity = web_sim_sum / max(web_count, 1)

        # Coverage metrics
        has_web = use_web_search and self.serper_api_key and web_count > 0
        has_local = use_local_kb and local_count > 0
        total_chunks = len(chunks)
        compared_chunks = total_chunks if (has_web or has_local) else 0

        # Self-similarity: internal paragraph redundancy
        self_sim = 0.0
        if len(chunks) >= 2:
            scores = []
            for i in range(len(chunks)):
                for j in range(i + 1, min(i + 5, len(chunks))):
                    scores.append(ngram_jaccard(chunks[i]["text"], chunks[j]["text"]))
            if scores: self_sim = round(sum(scores) / len(scores), 3)

        risk_level = _similarity_to_risk(total_similarity)
        sim_status = "sufficient" if (has_web or has_local) else "insufficient_coverage"
        cov_note = ""
        if sim_status == "insufficient_coverage":
            cov_note = "开放来源覆盖不足，暂未形成有效相似度结论。"
            if not self.serper_api_key: cov_note += "未配置 SERPER_API_KEY，无法进行网络搜索。"
            if not has_local: cov_note += "本地知识库无参考文档。"
            cov_note += f" 文档内部段落自相似度为 {self_sim*100:.1f}%。"
            risk_level = "medium"

        summary = _build_plagiarism_summary(total_similarity, len(segments), len(chunks))
        if sim_status == "insufficient_coverage":
            summary = cov_note

        return {
            "total_similarity": round(total_similarity, 3),
            "local_similarity": round(local_similarity, 3),
            "web_similarity": round(web_similarity, 3),
            "self_similarity": self_sim,
            "risk_level": risk_level,
            "similarity_status": sim_status,
            "coverage": round(compared_chunks / max(total_chunks, 1), 3),
            "coverage_note": cov_note,
            "total_chunks": total_chunks,
            "compared_chunks": compared_chunks,
            "summary": summary,
            "segments": segments,
            "disclaimer": "本结果为开放来源相似度预审，不等同正式查重。不能替代知网、维普、万方、Turnitin等正式查重系统。覆盖不足时仅供参考。",
        }

    def _search_web_for_chunk(self, chunk_text: str) -> List[Dict[str, Any]]:
        """对单个 chunk 执行网络搜索"""
        if not self.serper_api_key:
            return []
        query = select_representative_query(chunk_text, max_len=35)
        if len(query) < 10:
            return []
        try:
            import http.client
            import json
            conn = http.client.HTTPSConnection("google.serper.dev", timeout=10)
            payload = json.dumps({"q": query, "gl": "cn", "hl": "zh-cn"})
            headers = {
                "X-API-KEY": self.serper_api_key,
                "Content-Type": "application/json",
            }
            conn.request("POST", "/search", payload, headers)
            resp = conn.getresponse()
            if resp.status != 200:
                conn.close()
                return []
            data = json.loads(resp.read().decode("utf-8"))
            conn.close()

            results: List[Dict[str, Any]] = []
            for item in data.get("organic", [])[:3]:
                snippet = item.get("snippet", "")
                sim = compute_comprehensive_similarity(chunk_text, snippet)
                if sim > 0.2:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("link", ""),
                        "source_type": "web",
                        "similarity": round(sim, 3),
                        "snippet": snippet[:200],
                    })
            return results
        except Exception as e:
            LOGGER.warning("Web search for chunk failed: %s", e)
            return []

    def _check_web_similarity(self, chunk_text: str) -> float:
        """检查单个 chunk 的网络相似度（只返回最高分）"""
        if not self.serper_api_key:
            return 0.0
        query = select_representative_query(chunk_text, max_len=35)
        if len(query) < 10:
            return 0.0
        try:
            import http.client
            import json
            conn = http.client.HTTPSConnection("google.serper.dev", timeout=10)
            payload = json.dumps({"q": query, "gl": "cn", "hl": "zh-cn"})
            headers = {
                "X-API-KEY": self.serper_api_key,
                "Content-Type": "application/json",
            }
            conn.request("POST", "/search", payload, headers)
            resp = conn.getresponse()
            if resp.status != 200:
                conn.close()
                return 0.0
            data = json.loads(resp.read().decode("utf-8"))
            conn.close()

            max_sim = 0.0
            for item in data.get("organic", [])[:3]:
                snippet = item.get("snippet", "")
                sim = compute_comprehensive_similarity(chunk_text, snippet)
                if sim > max_sim:
                    max_sim = sim
            return max_sim
        except Exception:
            return 0.0


def _similarity_to_risk(sim: float) -> str:
    if sim <= 0.15:
        return "low"
    elif sim <= 0.30:
        return "medium"
    elif sim <= 0.50:
        return "high"
    return "critical"


def _build_reason(sim: float, sources: List[Dict[str, Any]]) -> str:
    if sim <= 0.15:
        return "该段落未发现明显相似内容。"
    if sources:
        top = sources[0]
        stype = "本地知识库" if top.get("source_type") == "local_knowledge_base" else "网络来源"
        return f"该段与{stype}「{top.get('title', '未知来源')[:30]}」存在表达相似。"
    return "该段落存在一定相似风险，建议检查表述。"


def _build_suggestion(sim: float) -> str:
    if sim <= 0.15:
        return "可保持现有表述。"
    if sim <= 0.30:
        return "建议适当调整用词和句式，增加自己的分析视角。"
    if sim <= 0.50:
        return "建议重写该段落，重新组织论据逻辑，加强独立分析。"
    return "建议彻底重写该部分内容，重新梳理论证逻辑并加入原创分析。"


def _build_plagiarism_summary(total_sim: float, suspicious_count: int, total_chunks: int) -> str:
    pct = round(total_sim * 100, 1)
    if total_sim <= 0.15:
        return f"本文开放来源相似度为 {pct}%，整体处于较低水平。在 {total_chunks} 个分析段落中，有 {suspicious_count} 个段落存在轻微相似。"
    elif total_sim <= 0.30:
        return f"本文开放来源相似度为 {pct}%，存在若干段落与开放来源表达相似。在 {total_chunks} 个分析段落中，有 {suspicious_count} 个段落需要关注。"
    elif total_sim <= 0.50:
        return f"本文开放来源相似度为 {pct}%，存在较多疑似重复段落。在 {total_chunks} 个分析段落中，有 {suspicious_count} 个段落相似度较高，建议重点修改。"
    return f"本文开放来源相似度为 {pct}%，存在严重相似风险。在 {total_chunks} 个分析段落中，有 {suspicious_count} 个段落高度相似，需要全面重写。"


# 全局实例
plagiarism_service = PlagiarismService()
