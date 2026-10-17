"""本地论文查重模块（复刻 paper_checking_system 的核心算法）

算法依据（paper_checking_system README「查重原理说明」）：
- 每两篇文本之间比对**连续相同的字符串**，连续相同字数超过阈值（推荐 10~16，默认 13）即判定为重复；
- 单篇重复率极低（<0.25%）或重复字数过少（<30 字）不判定为重复；
- 同一句话被复制多次，只计一次重复；
- 文本格式化时去掉摘要/目录/参考文献及非中文字符。

本模块在**无网络、无外部 API key** 的情况下也能给出真实、可复现的查重结果，包含两类：
1. 纵向查重：与本地比对库（backend/data/public/documents 下的题录/全文文本）逐篇比对；
2. 横向自查重：检测论文内部反复出现的句段（自我抄袭 / 复制粘贴 / 摘要-结论重复）。

输出结构与 plagiarism_service.detect_plagiarism 兼容，可直接放进 result["plagiarism"]。
"""

from __future__ import annotations

import glob
import logging
import os
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

LOGGER = logging.getLogger(__name__)

# 连续相同字数阈值（paper_checking 推荐 10~16）
DEFAULT_NGRAM = 13
# 单段重复字数低于该值不计（paper_checking: 30 字）
MIN_REPEAT_CHARS = 30
# 单篇重复率低于该比例不计（paper_checking: 0.25%）
MIN_REPEAT_RATIO = 0.0025

_CJK_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")


def _fingerprint_text(text: str) -> str:
    """格式化：只保留中文、英文、数字（去掉标点/空白/符号），与 paper_checking 一致。"""
    return "".join(_CJK_RE.findall(text or ""))


def _split_sentences(text: str) -> List[Tuple[int, int, str]]:
    """按中文句读/换行切句，返回 (原文起始, 原文结束, 句子原文)。"""
    sentences: List[Tuple[int, int, str]] = []
    buf: List[str] = []
    start = 0
    for i, ch in enumerate(text):
        buf.append(ch)
        if ch in "。！？；\n" or (ch in "，,;:" and False):
            seg = "".join(buf).strip()
            if seg:
                sentences.append((start, i + 1, seg))
            buf = []
            start = i + 1
    seg = "".join(buf).strip()
    if seg:
        sentences.append((start, len(text), seg) if start < len(text) else (start, len(text), seg))
    return sentences


def _ngrams(s: str, n: int) -> List[str]:
    if len(s) < n:
        return []
    return [s[i:i + n] for i in range(len(s) - n + 1)]


def _strip_sections(text: str) -> str:
    """去掉参考文献、致谢、附录等尾注部分，避免把文献条目误判为重复（paper_checking 做法）。"""
    cut = len(text)
    for m in re.finditer(r"\n\s*(参\s*考\s*文\s*献|References|REFERENCES|致\s*谢|附\s*录|Appendix)", text):
        if m.start() > len(text) * 0.4:  # 只采信出现在正文 40% 之后的标题
            cut = min(cut, m.start())
    return text[:cut]


_REF_TYPE_RE = re.compile(r"\[(J|M|C|D|R|N|S|P|EB/OL|DB/OL|DB/MT)\]")
_REF_LEAD_RE = re.compile(r"^\s*((\[\d+\])|([①-⑳㉑-㊿])|(\d+[\.、]))")


def _is_reference_line(sent: str) -> bool:
    """判断是否为参考文献/脚注条目（这类跨处重复是引用，不算作者抄袭）。"""
    t = (sent or "").strip()
    if not t:
        return True
    if _REF_TYPE_RE.search(t):  # 含 [J]/[M]/[EB/OL] 等文献类型标识
        return True
    if _REF_LEAD_RE.match(t) and (("：" in t) or (":" in t) or len(t) < 220):
        return True
    if t.startswith(("http://", "https://")) or ("DOI" in t and "doi" in t.lower()):
        return True
    # 形如「作者. 题名[J]. 期刊」的文献条目：含多个英文句点且很短
    if len(t) < 180 and t.count(".") >= 2 and re.search(r"(19|20)\d{2}", t) and _CJK_RE.search(t[1:3] or " "):
        return True
    return False


class LocalDuplicateChecker:
    """本地连续 N 字指纹查重。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._corpus: Optional[List[Dict[str, Any]]] = None

    # ------------------------------------------------------------------
    # 本地比对库
    # ------------------------------------------------------------------
    def _corpus_dirs(self) -> List[str]:
        here = os.path.dirname(os.path.abspath(__file__))
        root = os.path.abspath(os.path.join(here, "..", "..", "data"))
        candidates = [
            os.path.join(root, "public", "documents"),
            os.path.join(root, "local_compare_corpus"),
        ]
        return [c for c in candidates if os.path.isdir(c)]

    def _load_corpus(self) -> List[Dict[str, Any]]:
        with self._lock:
            if self._corpus is not None:
                return self._corpus
            corpus: List[Dict[str, Any]] = []
            seen_names = set()
            for d in self._corpus_dirs():
                for path in glob.glob(os.path.join(d, "**", "*.txt"), recursive=True):
                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            raw = f.read()
                    except Exception:
                        continue
                    norm = _fingerprint_text(raw)
                    if len(norm) < 40:
                        continue
                    name = os.path.splitext(os.path.basename(path))[0]
                    if name in seen_names:
                        continue
                    seen_names.add(name)
                    grams = set(_ngrams(norm, DEFAULT_NGRAM))
                    if not grams:
                        continue
                    corpus.append({"name": name, "norm": norm, "grams": grams, "raw": raw})
            self._corpus = corpus
            LOGGER.info("local compare corpus loaded: %d docs", len(corpus))
            return corpus

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def check(self, raw_text: str, use_corpus: bool = True) -> Dict[str, Any]:
        body = _strip_sections(raw_text or "")
        norm = _fingerprint_text(body)
        total_chars = len(norm)
        if total_chars < DEFAULT_NGRAM:
            return self._empty_result()

        n = DEFAULT_NGRAM
        doc_grams_list = _ngrams(norm, n)
        total_grams = len(doc_grams_list)

        # 字符覆盖标记：norm 中每个字符是否被判为重复
        cover_corpus = [False] * total_chars
        cover_self = [False] * total_chars
        segments: List[Dict[str, Any]] = []

        sentences = [s for s in _split_sentences(body) if not _is_reference_line(s[2])]

        # --------------------------------------------------------------
        # 1) 纵向查重：与本地比对库逐篇比对连续相同片段
        # --------------------------------------------------------------
        corpus_hits: List[Dict[str, Any]] = []
        if use_corpus:
            corpus = self._load_corpus()
            # 全局库指纹 -> 命中快速判断
            if corpus:
                # 逐句找命中的库文档与连续片段
                for (s0, s1, sent) in sentences:
                    snorm = _fingerprint_text(sent)
                    if len(snorm) < n:
                        continue
                    sgrams = _ngrams(snorm, n)
                    best = None  # (doc, 命中指纹数, 连续片段)
                    for doc in corpus:
                        hit_idx = [i for i, g in enumerate(sgrams) if g in doc["grams"]]
                        if not hit_idx:
                            continue
                        # 最长连续命中区间（指纹索引连续 => 原文连续相同）
                        runs = self._runs(hit_idx)
                        longest = max(runs, key=lambda r: r[1] - r[0])
                        run_len = longest[1] - longest[0] + 1
                        # 连续相同字数 ≈ run_len + n - 1
                        same_chars = run_len + n - 1
                        if same_chars < MIN_REPEAT_CHARS:
                            continue
                        if best is None or same_chars > best[1]:
                            # 映射回库原文的一段文字作为 snippet
                            snippet = self._recover_snippet(doc["norm"], sgrams[longest[0]], same_chars)
                            best = (doc, same_chars, snippet, len(hit_idx))
                    if best:
                        doc, same_chars, snippet, hit_cnt = best
                        sim = min(1.0, same_chars / max(len(snorm), 1))
                        corpus_hits.append({
                            "sent": sent,
                            "span": (s0, s1),
                            "doc": doc["name"],
                            "same_chars": same_chars,
                            "sim": sim,
                            "snippet": snippet,
                        })
                        self._mark_cover(body, sent, snorm, norm, cover_corpus, mark_all=True)

        # --------------------------------------------------------------
        # 2) 横向自查重：论文内部句段重复（同句多次出现只计一次）
        # --------------------------------------------------------------
        # 指纹 -> 出现过的句子下标
        gram_to_sents: Dict[str, List[int]] = {}
        sent_norms: List[str] = []
        for idx, (_, _, sent) in enumerate(sentences):
            sn = _fingerprint_text(sent)
            sent_norms.append(sn)
            if len(sn) < n:
                continue
            for g in set(_ngrams(sn, n)):
                gram_to_sents.setdefault(g, []).append(idx)

        self_hits: List[Dict[str, Any]] = []
        for idx, (s0, s1, sent) in enumerate(sentences):
            sn = sent_norms[idx]
            if len(sn) < n:
                continue
            shared: Dict[int, int] = {}  # 其他句 -> 共享指纹数
            for g in set(_ngrams(sn, n)):
                for other in gram_to_sents.get(g, []):
                    if other != idx:
                        shared[other] = shared.get(other, 0) + 1
            if not shared:
                continue
            other_idx, cnt = max(shared.items(), key=lambda kv: kv[1])
            same_chars = cnt + n - 1
            if same_chars < MIN_REPEAT_CHARS:
                continue
            # 与该句的相似度（按较短句归一）
            base = max(len(sn), 1)
            sim = min(1.0, same_chars / base)
            if sim < 0.30:
                continue
            self_hits.append({
                "sent": sent,
                "span": (s0, s1),
                "other": other_idx + 1,
                "same_chars": same_chars,
                "sim": sim,
            })
            self._mark_cover(body, sent, sn, norm, cover_self, mark_all=False, shared_cnt=cnt)

        # --------------------------------------------------------------
        # 汇总覆盖率（重复字数 / 总字数）
        # --------------------------------------------------------------
        corpus_chars = sum(cover_corpus)
        self_chars = sum(cover_self)
        union_chars = sum(1 for a, b in zip(cover_corpus, cover_self) if a or b)

        local_similarity = corpus_chars / max(total_chars, 1)
        self_similarity = self_chars / max(total_chars, 1)
        total_similarity = union_chars / max(total_chars, 1)

        # --------------------------------------------------------------
        # 组装 segments（兼容前端契约）
        # --------------------------------------------------------------
        seg_index = 0
        for h in corpus_hits:
            seg_index += 1
            seg_index_no = seg_index
            segments.append({
                "index": seg_index_no,
                "text": h["sent"][:240],
                "start_char": h["span"][0],
                "end_char": h["span"][1],
                "similarity_score": round(h["sim"], 3),
                "risk_level": self._risk(h["sim"]),
                "matched_sources": [{
                    "title": f"本地比对库：{h['doc']}",
                    "url": "",
                    "source_type": "local_corpus",
                    "similarity": round(h["sim"], 3),
                    "snippet": h["snippet"],
                }],
                "reason": f"该段与本地文献《{h['doc']}》存在连续约 {h['same_chars']} 字相同表述。",
                "suggestion": self._suggest(h["sim"]),
                "check_type": "corpus",
            })

        for h in self_hits:
            seg_index += 1
            segments.append({
                "index": seg_index,
                "text": h["sent"][:240],
                "start_char": h["span"][0],
                "end_char": h["span"][1],
                "similarity_score": round(h["sim"], 3),
                "risk_level": self._risk(h["sim"]),
                "matched_sources": [{
                    "title": f"本文内部重复（与第 {h['other']} 处表述雷同）",
                    "url": "",
                    "source_type": "self_duplicate",
                    "similarity": round(h["sim"], 3),
                    "snippet": "论文内部不同位置出现大段相同/高度雷同表述",
                }],
                "reason": f"该段与本文第 {h['other']} 处表述连续约 {h['same_chars']} 字雷同，属于内部重复。",
                "suggestion": "摘要、正文与结论之间避免大段重复表述；同一观点在不同章节应换用不同措辞或仅保留一处完整论述。",
                "check_type": "self",
            })

        segments.sort(key=lambda x: x["similarity_score"], reverse=True)
        for i, s in enumerate(segments, 1):
            s["index"] = i

        # paper_checking: 整体重复率低于 0.25% 不判定为重复
        if total_similarity < MIN_REPEAT_RATIO and not segments:
            total_similarity = 0.0

        risk = self._risk(total_similarity)
        corpus_n = len(self._load_corpus()) if use_corpus else 0
        summary = self._summary(total_similarity, self_similarity, local_similarity,
                                len(segments), corpus_n)

        return {
            "total_similarity": round(total_similarity, 4),
            "local_similarity": round(local_similarity, 4),
            "web_similarity": 0.0,
            "self_similarity": round(self_similarity, 4),
            "corpus_size": corpus_n,
            "total_chars": total_chars,
            "duplicate_chars": union_chars,
            "risk_level": risk,
            "summary": summary,
            "segments": segments,
            "similarity_status": "sufficient",
            "check_method": f"连续{DEFAULT_NGRAM}字指纹（本地库纵向比对 + 文档内部横向自查重）",
            "disclaimer": (
                "本结果基于本地比对库与文档内部连续相同字符串算法（复刻 paper_checking 原理），"
                "不联网、不等同知网/维普/万方/Turnitin 正式查重，仅供修改参考。"
            ),
        }

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _runs(idx_sorted: List[int]) -> List[Tuple[int, int]]:
        """把命中的指纹索引列表合并为连续区间 (start,end)（含端点）。"""
        if not idx_sorted:
            return []
        idx = sorted(set(idx_sorted))
        runs = []
        s = p = idx[0]
        for x in idx[1:]:
            if x == p + 1:
                p = x
            else:
                runs.append((s, p))
                s = p = x
        runs.append((s, p))
        return runs

    @staticmethod
    def _recover_snippet(doc_norm: str, gram: str, same_chars: int) -> str:
        pos = doc_norm.find(gram)
        if pos < 0:
            return gram
        return doc_norm[pos:pos + same_chars + 12]

    @staticmethod
    def _mark_cover(body: str, sent: str, snorm: str, norm: str,
                    cover: List[bool], mark_all: bool, shared_cnt: int = 0) -> None:
        """在 norm 上定位该句并标记重复字符位置。"""
        pos = norm.find(snorm)
        if pos < 0:
            return
        end = pos + len(snorm)
        if mark_all:
            for i in range(pos, min(end, len(cover))):
                cover[i] = True
        else:
            # 内部重复：标记与 shared_cnt 对应的连续字符（近似取前 shared_cnt+n-1）
            length = min(len(cover), end, pos + shared_cnt + DEFAULT_NGRAM - 1)
            for i in range(pos, length):
                cover[i] = True

    @staticmethod
    def _risk(sim: float) -> str:
        if sim <= 0.15:
            return "low"
        if sim <= 0.30:
            return "medium"
        if sim <= 0.50:
            return "high"
        return "critical"

    @staticmethod
    def _suggest(sim: float) -> str:
        if sim <= 0.15:
            return "可保持现有表述。"
        if sim <= 0.30:
            return "建议调整用词与句式，增加自己的分析视角，并规范引用标注。"
        if sim <= 0.50:
            return "建议重写该段，重新组织论据逻辑，以自己的语言概括并加引号/脚注标注来源。"
        return "该段高度雷同，建议彻底重写，规范引用并补充原创分析，避免学术不端风险。"

    @staticmethod
    def _summary(total: float, self_s: float, local_s: float, n_seg: int, corpus_n: int) -> str:
        pct = f"{total * 100:.1f}%"
        if total < 0.0025 and n_seg == 0:
            base = f"本地查重未发现连续 {DEFAULT_NGRAM} 字以上的雷同片段，整体重复率约 {pct}。"
        elif total <= 0.15:
            base = f"本地查重整体重复率约 {pct}，处于较低水平，共定位 {n_seg} 处雷同片段。"
        elif total <= 0.30:
            base = f"本地查重整体重复率约 {pct}，存在若干雷同片段（{n_seg} 处），建议调整。"
        else:
            base = f"本地查重整体重复率约 {pct}，雷同片段较多（{n_seg} 处），需重点修改。"
        base += f"其中文档内部重复约 {self_s * 100:.1f}%、与本地比对库（{corpus_n} 篇）重合约 {local_s * 100:.1f}%。"
        return base

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "total_similarity": 0.0,
            "local_similarity": 0.0,
            "web_similarity": 0.0,
            "self_similarity": 0.0,
            "corpus_size": 0,
            "total_chars": 0,
            "duplicate_chars": 0,
            "risk_level": "low",
            "summary": "文稿有效字数过少，无法进行查重。",
            "segments": [],
            "similarity_status": "insufficient_coverage",
            "check_method": f"连续{DEFAULT_NGRAM}字指纹",
            "disclaimer": "本地查重结果，不等同正式查重系统。",
        }


# 全局单例
local_duplicate_checker = LocalDuplicateChecker()
