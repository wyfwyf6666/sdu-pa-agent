from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from openai import OpenAI

from backend.app.models.pre_review import (
    Annotation,
    ChecklistItem,
    MainIssue,
    ModuleResult,
    OverallAssessment,
    PreReviewResponse,
    RewriteExample,
    RiskWarning,
)

LOGGER = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[3]

# 核心审查维度（也是 annotation.module 的取值范围）
CORE_MODULES = ["depth", "language", "references", "format", "data_methods"]

MODULE_NAMES: Dict[str, str] = {
    "references": "文献核查",
    "depth": "深度审稿",
    "language": "语言检查",
    "literature": "建议文献",
    "reviewers": "建议审稿人",
    "journals": "建议期刊",
    "comparison": "过刊比较",
    "translation": "文档翻译",
    "format": "格式规范检查",
    "data_methods": "数据来源与研究方法建议",
}

MODULE_GUIDANCE: Dict[str, str] = {
    "depth": "全文逻辑链是否闭环：绪论提出的研究问题后文是否逐一回应、结论是否呼应研究目标；论点是否有数据/证据支撑而非空断；论点与所引数据是否匹配；章节间有无逻辑跳跃或断裂；研究问题是否聚焦、行文有无偏移；各部分是否自相矛盾",
    "language": "AI 生成痕迹与学术表达：空泛肯定句（如'取得显著成效''具有重要意义'却无任何数据支撑）、异常高频的总结连接词（综上所述/值得注意的是/由此可见）、过于工整的'首先其次最后'三段式、学术黑话堆砌（赋能/深度融合/多维度/范式）、口号化套话；以及错别字、语病、口语化、术语前后不一致",
    "references": "文献综述是否沦为流水账（逐篇罗列、缺少按方法/问题的分类组织、缺少横向对比与作者本人评述、未指出研究空白）；正文引用与文末文献列表是否双向对应；引用是否真正支撑该论点而非装饰；核心观点是否缺引；文献是否陈旧；格式是否统一",
    "format": "摘要是否具备目的/方法/结果/结论四要素且字数得当；研究方法是否单设并交代数据来源、样本/案例选择与分析方法；图表是否有编号标题并在正文被引用；结论是否点明研究局限与具体展望而非空泛收尾；标题层级与结构是否完整",
    "data_methods": "数据来源、样本/案例选择是否交代清楚且可复核；研究方法与研究问题是否匹配；分析是否有对比或基准而非只摆数据；结果是否支持前文提出的假设或问题；异常/负面结果是否有解释；关键步骤是否具备可复现性",
}

SYSTEM_PROMPT = """你是"山大政管·砺文智审系统"，隶属于山东大学政治学与公共管理学院场景下的论文智能预审与学术写作辅助智能体。

你的核心定位：
- 你是严谨、专业、温和但不敷衍的学术预审助手，服务政治学、公共管理、公共政策、行政管理、基层治理、城市治理、数字政府、公共服务、社会治理、应急管理等方向
- 你的任务是在论文、课程论文、选题报告、实训报告、投稿初稿提交前，给出基于原文证据的、具体的、可执行的预审意见

重要限制：
1. 不得编造参考文献、期刊信息、审稿人姓名、导师姓名或学校内部规定
2. 不得承诺论文一定通过、一定发表或一定降低查重率
3. 如果用户要求代写整篇论文，应拒绝直接代写，可以改为提供提纲修改建议
4. 涉及学校具体格式、学院内部要求、课程要求，应提醒用户以任课教师或学院正式通知为准

审稿风格：
- 像一位逐句读完稿件的预审老师：只谈你在这篇稿件里真正看到的问题，每条意见都要能指回原文
- 不堆术语、不写放之四海皆准的套话，不因为"模板里有这一项"就硬凑意见
- 没有问题的地方明确放行，问题多的地方集中指出
"""

# 审查中禁止出现的无证据套话（仅当不结合原文具体细节时）
CLICHE_PHRASES = [
    "逻辑不够清晰", "逻辑较为混乱", "建议加强理论分析", "研究深度不足",
    "结构有待完善", "语言不够学术化", "内容不够充实", "论述不够充分",
    "具有重要意义", "具有重要的理论意义和现实意义", "建议进一步完善",
    "有待进一步研究", "提出了宝贵意见", "奠定了坚实基础",
]


def _normalize_match(text: str) -> str:
    """归一化用于摘录匹配：去空白、统一引号。"""
    if not text:
        return ""
    text = re.sub(r"\s+", "", text)
    # 统一常见中英文标点差异
    pairs = {
        "“": '"', "”": '"', "‘": "'", "’": "'",
        "，": ",", "。": ".", "；": ";", "：": ":", "（": "(", "）": ")",
        "【": "[", "】": "]", "？": "?", "！": "!", "、": ",",
    }
    for k, v in pairs.items():
        text = text.replace(k, v)
    return text


def _strip_code_fence(text: str) -> str:
    """去掉 LLM 输出可能包裹的 ```json ... ``` 代码块。"""
    t = (text or "").strip()
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", t, re.DOTALL)
    return m.group(1).strip() if m else t


def _heal_json_quotes(text: str) -> str:
    """修复 JSON 字符串值内部未转义的裸双引号（LLM 偶发在中文句子里直接写 "）。

    判定：一个双引号若其后（跳过空白）紧跟结构符 : , } ] 或文本结束，才是字符串闭合；
    否则视为字符串内部的裸引号，转义为 \\"。
    """
    out: List[str] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch != '"':
            out.append(ch)
            i += 1
            continue
        # 进入字符串，找真正的闭合引号
        buf = ['"']
        j = i + 1
        while j < n:
            c = text[j]
            if c == "\\":
                buf.append(c)
                if j + 1 < n:
                    buf.append(text[j + 1])
                    j += 2
                    continue
                j += 1
                continue
            if c == '"':
                k = j + 1
                while k < n and text[k] in " \t\r\n":
                    k += 1
                if k >= n or text[k] in ":},]":
                    buf.append('"')
                    j += 1
                    break
                buf.append('\\"')
                j += 1
                continue
            buf.append(c)
            j += 1
        out.append("".join(buf))
        i = j
    return "".join(out)


def _balance_json_text(text: str) -> Optional[str]:
    """从首个 {/[ 开始，按字符串感知方式补全被截断的括号与引号。"""
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        return None
    s = text[min(starts):]
    stack: List[str] = []
    in_str = False
    escape = False
    close_of = {"{": "}", "[": "]"}
    for ch in s:
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            want = "{" if ch == "}" else "["
            if stack and stack[-1] == want:
                stack.pop()
    suffix = ('"' if in_str else "") + "".join(close_of[b] for b in reversed(stack))
    return s + suffix


def _extract_json_objects(text: str) -> List[Dict[str, Any]]:
    """字符串感知扫描，抢救所有平衡的 {...} 对象并逐个解析（用于截断 JSON）。"""
    objs: List[Dict[str, Any]] = []
    opens: List[int] = []
    in_str = False
    escape = False
    for i, ch in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            opens.append(i)
        elif ch == "}" and opens:
            start = opens.pop()
            try:
                val = json.loads(text[start:i + 1])
                if isinstance(val, dict):
                    objs.append(val)
            except json.JSONDecodeError:
                continue
    return objs


def _repair_truncated_json(text: str) -> Any:
    """在安全边界（逗号/闭合括号）处逐档回退截断点并补全，尽量保住最外层对象。"""
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        return None
    s = text[min(starts):]
    cuts: List[int] = []
    in_str = False
    escape = False
    for i, ch in enumerate(s):
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in ",}]":
            # 逗号切在它之前，闭合括号切在它之后
            cuts.append(i if ch == "," else i + 1)
    for cut in reversed(cuts):
        balanced = _balance_json_text(s[:cut])
        if not balanced:
            continue
        try:
            return json.loads(balanced)
        except json.JSONDecodeError:
            continue
    balanced = _balance_json_text(s)
    if balanced:
        try:
            return json.loads(balanced)
        except json.JSONDecodeError:
            return None
    return None


class PreReviewService:
    def __init__(self):
        self.review_cache: Dict[str, Dict[str, Any]] = {}
        # 按优先级查找有效的 API Key
        candidates = [
            (os.getenv("DASHSCOPE_API_KEY", ""), os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")),
            (os.getenv("OPENAI_API_KEY", ""), os.getenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")),
        ]
        api_key = ""
        base_url = ""
        for key, url in candidates:
            if key and "your_" not in key and key.strip():
                api_key = key.strip()
                base_url = url
                break

        model = os.getenv("PRE_REVIEW_MODEL", "deepseek-chat")
        self.llm_model = model
        self.llm_client = None
        self.llm_available = False
        if api_key:
            try:
                self.llm_client = OpenAI(api_key=api_key, base_url=base_url)
                self.llm_available = True
                LOGGER.info("PreReview LLM client initialized: model=%s, base_url=%s", model, base_url)
            except Exception as e:
                LOGGER.warning("Failed to init LLM client: %s", e)

    # ------------------------------------------------------------------
    # 文本处理
    # ------------------------------------------------------------------
    def _split_paragraphs(self, manuscript: str) -> List[str]:
        """把原始文稿切分为带语义的段落，供编号展示与意见定位。

        兼容正常粘贴文本（空行分段）与 PDF 抽取文本（段内硬换行）。
        """
        text = manuscript.replace("\r\n", "\n").replace("\r", "\n").strip()
        lines = [ln.strip() for ln in text.split("\n")]
        heading_re = re.compile(
            r"^(摘\s*要|关键词|关\s*键\s*词|Abstract|Key\s*words?|引言|前言|引\s*言|"
            r"参考文献|结\s*论|讨论|致谢|附录|"
            r"[一二三四五六七八九十百]+[、.．]\s*\S|"
            r"（[一二三四五六七八九十]+）|\(\d+\)|\d+[.．、]\s*\S|"
            r"第[一二三四五六七八九十百]+[章节])"
        )
        paragraphs: List[str] = []
        buf = ""

        def flush() -> None:
            nonlocal buf
            if buf.strip():
                paragraphs.append(buf.strip())
            buf = ""

        for line in lines:
            if not line:
                flush()
                continue
            is_heading = len(line) <= 40 and bool(heading_re.match(line))
            if is_heading:
                flush()
                paragraphs.append(line)
                continue
            if not buf:
                buf = line
            elif len(buf) >= 300 and re.search(r"[。！？；…：”\"]$", buf):
                # 缓冲段已较长且在句末，视为 PDF 硬换行中的段落边界
                flush()
                buf = line
            else:
                buf += line
            if len(buf) >= 520:
                flush()
        flush()
        return paragraphs if paragraphs else [text]

    def _locate_quote(
        self, quote: str, paragraphs: List[str], hint: int
    ) -> Tuple[int, str, bool]:
        """在段落中定位摘录，返回 (段落1-based编号, 校正后的摘录, 是否精确匹配)。"""
        quote = (quote or "").strip()
        if not quote:
            return (hint if hint >= 1 else -1, "", False)
        if len(quote) > 200:
            quote = quote[:200]

        n = len(paragraphs)

        def direct_in(text: str, q: str) -> bool:
            return q and q in text

        def norm_in(text: str, q: str) -> bool:
            nq = _normalize_match(q)
            return bool(nq) and nq in _normalize_match(text)

        # 候选段落顺序：提示段 → 全文
        order: List[int] = []
        if 1 <= hint <= n:
            order.append(hint - 1)
        for i in range(n):
            if i not in order:
                order.append(i)

        # 1) 直接 / 归一化子串匹配
        for idx in order:
            p = paragraphs[idx]
            if direct_in(p, quote) or norm_in(p, quote):
                return idx + 1, quote, True

        # 2) 模糊匹配：bigram 覆盖率粗筛候选段 + 有界滑窗精排。
        #    长文 / OCR 文本的摘录与原文之间有错字、空格、换行差异，直接匹配往往
        #    不命中；此时若对每条意见都在大量段落上逐滑窗算 SequenceMatcher，
        #    复杂度会爆炸并占满 CPU。这里先用 O(len) 的二元组覆盖率筛出最相似的
        #    少数段落，再在严格的窗口数预算内做相似度精排，保证耗时有上界。
        nq_all = _normalize_match(quote)
        if len(nq_all) >= 8:
            FUZZ_Q_MAX = 40
            nq = nq_all[:FUZZ_Q_MAX] if len(nq_all) > FUZZ_Q_MAX else nq_all

            def _bigrams(s: str) -> set:
                if len(s) >= 2:
                    return {s[i : i + 2] for i in range(len(s) - 1)}
                return {s} if s else set()

            qbg = _bigrams(nq)

            # 2a) 粗筛：按摘录二元组被覆盖的比例对候选段排序（线性、廉价）
            ranked: List[Tuple[float, int, str]] = []
            if qbg:
                for rank, idx in enumerate(order[: min(len(order), 80)]):
                    np_text = _normalize_match(paragraphs[idx])
                    if len(np_text) < len(nq) * 0.6:
                        continue
                    cov = len(qbg & _bigrams(np_text)) / len(qbg)
                    if rank == 0 and 1 <= hint <= n:
                        cov += 0.05  # 模型给出的提示段轻微加权
                    ranked.append((cov, idx, np_text))
            ranked.sort(key=lambda x: x[0], reverse=True)

            # 2b) 精排：仅最相似的若干段、硬上限窗口数；先用覆盖率廉价过滤，
            #     只有像样的窗口才计算 SequenceMatcher。
            best: Tuple[float, int, str] = (0.0, -1, "")
            budget = 0
            MAX_WINDOWS = 300
            win = len(nq)
            step = max(8, win // 2)
            for _cov0, idx, np_text in ranked[:6]:
                for start in range(0, max(1, len(np_text) - win + 1), step):
                    seg = np_text[start : start + win]
                    budget += 1
                    if abs(len(seg) - win) <= max(6, win * 0.25):
                        cov = len(qbg & _bigrams(seg)) / max(1, len(qbg))
                        if cov >= 0.5:
                            ratio = SequenceMatcher(None, seg, nq, autojunk=False).ratio()
                            if ratio > best[0]:
                                best = (ratio, idx, seg)
                    if budget >= MAX_WINDOWS:
                        break
                if budget >= MAX_WINDOWS:
                    break

            if best[0] >= 0.72 and best[1] >= 0:
                # 模糊命中只用于把意见归到正确段落；摘录保留模型原文，
                # 避免 OCR/归一化窗口映射出的残片替换掉原 quote。
                return best[1] + 1, quote, False

        return (hint if 1 <= hint <= n else -1), quote, False

    @staticmethod
    def _slice_original(original: str, normalized_window: str) -> str:
        """根据归一化窗口，从原文中近似截取对应原始文字。"""
        if not normalized_window:
            return ""
        target = _normalize_match(original)
        pos = target.find(normalized_window)
        if pos < 0:
            # 退化：直接返回原文前一段长度内容
            return original[: len(normalized_window) + 20]
        # 建立归一化索引 → 原文索引映射
        mapping: List[int] = []
        for oi, ch in enumerate(original):
            nch = re.sub(r"\s+", "", ch)
            trans = {
                "“": '"', "”": '"', "‘": "'", "’": "'",
                "，": ",", "。": ".", "；": ";", "：": ":", "（": "(", "）": ")",
                "【": "[", "】": "]", "？": "?", "！": "!", "、": ",",
            }
            nch = trans.get(nch, nch)
            if nch:
                mapping.append(oi)
        end = min(pos + len(normalized_window), len(mapping))
        if pos >= len(mapping) or end == 0:
            return original[: len(normalized_window) + 20]
        return original[mapping[pos] : mapping[end - 1] + 1].strip()

    # ------------------------------------------------------------------
    # LLM 调用
    # ------------------------------------------------------------------
    def _call_llm(self, user_prompt: str, system_prompt: str = "", temperature: float = 0.3, max_tokens: int = 4096) -> str:
        if not self.llm_client or not self.llm_available:
            return "{}"
        full_system = SYSTEM_PROMPT + "\n\n" + system_prompt if system_prompt else SYSTEM_PROMPT
        try:
            resp = self.llm_client.chat.completions.create(
                model=self.llm_model,
                messages=[
                    {"role": "system", "content": full_system},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=180,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            LOGGER.error("LLM call failed: %s", e)
            return "{}"

    async def _async_call_llm(self, user_prompt: str, system_prompt: str = "", temperature: float = 0.3, max_tokens: int = 4096) -> str:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: self._call_llm(user_prompt, system_prompt, temperature, max_tokens))

    def _parse_json_safe(self, text: str) -> Any:
        """健壮解析 LLM 的 JSON 输出：代码块、整体截断、尾部元素截断均可抢救。"""
        text = _strip_code_fence(text)
        if not text:
            return {}
        # 1) 直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # 2) 修复字符串内部未转义的裸双引号后解析
        try:
            healed = _heal_json_quotes(text)
            if healed != text:
                return json.loads(healed)
        except json.JSONDecodeError:
            pass
        # 3) 括号/引号补全后解析（修复输出在结尾被截断）
        balanced = _balance_json_text(text)
        if balanced:
            try:
                return json.loads(balanced)
            except json.JSONDecodeError:
                pass
        # 3.5) 裸引号修复 + 截断补全组合
        try:
            combo = _balance_json_text(_heal_json_quotes(text))
            if combo:
                return json.loads(combo)
        except json.JSONDecodeError:
            pass
        # 3) 在安全边界回退截断点并补全，尽量保住最外层对象（overall/action 等）
        repaired = _repair_truncated_json(text)
        if repaired is not None:
            return repaired
        # 4) 证据审稿数组：逐个抢救已完整写出的 annotation 对象
        if "annotations" in text or "issue" in text or "quote" in text:
            objects = _extract_json_objects(text)
            for obj in objects:
                if isinstance(obj.get("annotations"), list):
                    return obj
            ann_like = [o for o in objects if ("issue" in o or "quote" in o)]
            if ann_like:
                return ann_like
        return {}

    # ------------------------------------------------------------------
    # 离线基础统计（无 API Key 兜底）
    # ------------------------------------------------------------------
    def _offline_text_stats(self, manuscript: str) -> Dict[str, Any]:
        text = manuscript.strip()
        chars = len(text)
        has_abstract = bool(re.search(r"(摘\s*要|Abstract)", text))
        has_keywords = bool(re.search(r"(关键词|Keywords)", text))
        has_intro = bool(re.search(r"(引言|前言|一[、.]\s*研究背景|一[、.]\s*引言|一[、.]\s*问题)", text))
        has_methods = bool(re.search(r"(研究方法|数据来源|样本|问卷|访谈|案例分析|实证)", text))
        has_conclusion = bool(re.search(r"(结论|建议|启示|展望|讨论)", text))
        ref_matches = re.findall(r"\[\d+\]", text)
        ref_count = len(set(ref_matches))

        score = 40
        if has_abstract: score += 10
        if has_keywords: score += 5
        if has_intro: score += 10
        if has_methods: score += 15
        if has_conclusion: score += 10
        if ref_count >= 5: score += 10
        if chars > 3000: score += 5
        # 篇幅严重不足时封顶，避免"有关键词就高分"
        if chars < 1000:
            score = min(score, 52)
        elif chars < 2000:
            score = min(score, 64)
        score = min(score, 95)
        return {
            "chars": chars,
            "has_abstract": has_abstract,
            "has_keywords": has_keywords,
            "has_intro": has_intro,
            "has_methods": has_methods,
            "has_conclusion": has_conclusion,
            "ref_count": ref_count,
            "score": score,
        }

    # ------------------------------------------------------------------
    # 核心：证据驱动的逐段审稿
    # ------------------------------------------------------------------
    EVIDENCE_SYSTEM = """本次任务是"逐段证据审稿"。请严格遵守：

【证据铁律】
1. 每一条意见必须包含 quote 字段：从原文中逐字摘录的 15-80 个汉字（含原标点），必须能在原文中一字不差地检索到。严禁改写、拼接、概括或虚构摘录。
2. issue 字段必须紧扣 quote：先说这段摘录具体哪里有问题、为什么构成问题，必须提到摘录中的具体概念、数字或表述；禁止只写"逻辑不清晰""建议加强分析"这类放在任何论文上都成立的话。
3. suggestion 字段必须给出针对这句话/这一段的具体改法（补什么数据、换成什么写法、增删什么内容、查什么文献），要可以照着动手改。
4. 宁缺毋滥：只报告你在这篇稿件中确实看到的问题；某个维度没有问题就一条都不要写；严禁多条意见表达同一个意思。
5. 全文覆盖：请通读给出的全部段落，问题可能出现在任意位置，不要只评价开头和摘要。
6. 每篇稿件的问题都不同。如果你的一条意见删掉稿件标题后仍适用于任意论文，说明它是套话，必须重写或删除。

【审查视角——优先于错别字/标点】
你是有 20 年硕博论文评审经验的预审老师。在这批段落里，请重点从以下学术实质层面找问题，而不是停留在语法：
1. 逻辑与证据：这段提出的判断有没有对应的数据、案例或文献支撑？论点和它后面引用的数据是否对得上？是否存在"结论先行、论据悬空"？
2. 研究问题与闭环：这段讨论是否服务于论文开头提出的研究问题？有没有跑题、堆砌背景却不落到研究对象？
3. 文献综述质量：是否在逐篇罗列别人做了什么，却没有分类比较、没有作者自己的评述、也没有指出研究空白？
4. 方法与可复现：样本、数据来源、问卷/访谈/案例的选取依据是否交代清楚？别人能否照着重复？
5. 结果与分析：是否只罗列数字/现象却不解释说明了什么？有无对比或基准？负面或反常结果是否被解释？
6. 学术表达与 AI 痕迹：是否出现无数据支撑的空泛肯定（"成效显著""意义重大"）、高频总结套话（"综上所述""值得注意的是"）、过于工整的三段式、或"赋能/深度融合/多维度"等空洞黑话？
7. 结构与收束：摘要是否凑齐目的/方法/结果/结论？结论是否回应了开头的问题、是否点明局限、展望是否具体？

【严重度】严重=动摇研究成立性或必须修改（结论无证据、方法错误、文献造假、结构残缺）；一般=明显缺陷应当修改；建议=锦上添花。
【数量】每个批次控制在 8 条以内，按严重度排序，只保留最有价值的。
只输出 JSON，不要任何解释文字。"""

    def _build_numbered_block(self, paragraphs: List[str], start: int, end: int, char_budget: int = 7000) -> Tuple[int, int, str]:
        """构建编号段落文本块，返回 (end_index, text)。"""
        parts: List[str] = []
        used = 0
        i = start
        while i < end:
            piece = f"【P{i + 1}】{paragraphs[i]}"
            if used + len(piece) > char_budget and parts:
                break
            parts.append(piece)
            used += len(piece)
            i += 1
        return i, "\n".join(parts)

    def _evidence_review_batch(
        self, title: str, doc_type: str, paragraphs: List[str], start: int, end: int
    ) -> List[Dict[str, Any]]:
        block_end, numbered = self._build_numbered_block(paragraphs, start, end)
        prompt = f"""文稿标题：《{title}》
文稿类型：{doc_type}
以下是文稿第 {start + 1}–{block_end} 段（段落编号即 paragraph 字段应填的数字）：

{numbered}

请逐段审查，输出 JSON：
{{
  "annotations": [
    {{
      "module": "depth|language|references|format|data_methods 之一",
      "severity": "严重|一般|建议",
      "paragraph": 段落编号整数,
      "quote": "从该段逐字摘录的原文",
      "issue": "紧扣摘录的具体问题（1-3句，必须出现摘录中的具体概念、数字或表述，不要铺垫）",
      "suggestion": "可直接照做的具体修改建议（1-2句，点明补什么/改成什么）"
    }}
  ]
}}

各模块关注：{'; '.join(f'{k}={v}' for k, v in MODULE_GUIDANCE.items())}
再次强调：quote 必须是原文原句，宁可不写也不要编造。"""
        def collect(raw_text: str) -> List[Dict[str, Any]]:
            parsed = self._parse_json_safe(raw_text)
            if isinstance(parsed, list):
                return [x for x in parsed if isinstance(x, dict)]
            if isinstance(parsed, dict):
                found = parsed.get("annotations", [])
                return [x for x in found if isinstance(x, dict)] if isinstance(found, list) else []
            return []

        raw = self._call_llm(prompt, self.EVIDENCE_SYSTEM, temperature=0.5, max_tokens=8192)
        items = collect(raw)
        if len(items) < 2:
            # 偶发返回过少或 JSON 异常时重试一次（提高温度并强调完整、合法输出）
            LOGGER.info("Evidence batch returned %d items, retrying once", len(items))
            retry_prompt = prompt + (
                "\n\n注意：上一次返回的意见过少或 JSON 不完整。请严格输出合法 JSON（字符串内部如需引用请使用中文引号“”，"
                "不要使用未转义的英文双引号），并给出 4-8 条带 quote 字段、覆盖不同段落与模块的 annotations。"
            )
            raw2 = self._call_llm(retry_prompt, self.EVIDENCE_SYSTEM, temperature=0.7, max_tokens=8192)
            items2 = collect(raw2)
            if len(items2) > len(items):
                items = items2
        return items

    def _validate_annotations(self, raw_items: List[Dict[str, Any]], paragraphs: List[str]) -> List[Annotation]:
        """校验、定位、去重 LLM 返回的意见。"""
        seen: set = set()
        result: List[Annotation] = []
        next_id = 1
        severity_rank = {"严重": 0, "一般": 1, "建议": 2}
        for item in raw_items:
            module = str(item.get("module", "")).strip()
            if module not in MODULE_GUIDANCE:
                # 容错：模型偶尔写中文模块名
                for k, v in MODULE_NAMES.items():
                    if module == v or module in v or v in module:
                        module = k
                        break
                else:
                    module = "depth"
            try:
                hint = int(item.get("paragraph", -1))
            except (TypeError, ValueError):
                hint = -1
            quote = str(item.get("quote", "")).strip()
            issue = str(item.get("issue", "")).strip()
            suggestion = str(item.get("suggestion", "")).strip()
            if not issue or len(issue) < 6:
                continue
            pidx, fixed_quote, matched = self._locate_quote(quote, paragraphs, hint)
            # 去重：同段落 + issue 前 18 字
            key = (pidx, re.sub(r"\s+", "", issue)[:18])
            if key in seen:
                continue
            seen.add(key)
            severity = str(item.get("severity", "")).strip()
            if severity not in ("严重", "一般", "建议"):
                severity = "一般"
            result.append(Annotation(
                id=next_id,
                module=module,
                module_name=MODULE_NAMES.get(module, module),
                severity=severity,
                paragraph=pidx,
                quote=fixed_quote if matched else (fixed_quote or quote),
                quote_matched=matched,
                issue=issue,
                suggestion=suggestion,
            ))
            next_id += 1
        result.sort(key=lambda a: (severity_rank.get(a.severity, 3), a.paragraph if a.paragraph > 0 else 9999))
        for i, ann in enumerate(result, 1):
            ann.id = i
        return result

    # ------------------------------------------------------------------
    # 总体评价 + 维度评分 + 投稿建议（一次调用）
    # ------------------------------------------------------------------
    def _overall_review(
        self, title: str, manuscript: str, doc_type_hint: str, annotations: List[Annotation]
    ) -> Dict[str, Any]:
        # 已发现问题摘要，帮助总体评价与逐条意见保持一致
        evidence_lines = [
            f"{i + 1}. [{a.module_name}/{a.severity}] {a.issue[:90]}"
            for i, a in enumerate(annotations[:18])
        ]
        evidence_text = "\n".join(evidence_lines) if evidence_lines else "（逐段审查未发现明显硬伤）"
        prompt = f"""请基于文稿全文和逐段审查发现，给出总体评价。所有结论必须来自这篇稿件本身，禁止套话。

文稿标题：《{title}》
文稿类型（供参考，可修正）：{doc_type_hint}

文稿全文（如过长为节选）：
{manuscript[:16000]}

逐段审查已发现的问题：
{evidence_text}

请输出 JSON：
{{
  "document_type": "选题报告/课程论文/实训报告/毕业论文/投稿论文/开题报告/摘要初稿/其他 之一",
  "completion_level": "3-4句完成度评价，必须点明本文具体的研究对象、所用方法和实际写到的内容，不得空泛",
  "overall_score": 0到100的整数,
  "strengths": ["必须提到本文具体内容（如某方法、某数据、某案例、某结论）的优点，2-4条"],
  "weaknesses": ["本文特有的短板，2-4条，每条要具体"],
  "priority": "一句话，最优先动手改的一件具体事情",
  "scores": [
    {{"label": "选题意义", "score": 整数, "note": "必须引用原文具体内容说明打分依据"}},
    {{"label": "理论基础", "score": 整数, "note": ""}},
    {{"label": "研究问题", "score": 整数, "note": ""}},
    {{"label": "研究方法", "score": 整数, "note": ""}},
    {{"label": "论证逻辑", "score": 整数, "note": ""}},
    {{"label": "实证与数据", "score": 整数, "note": ""}},
    {{"label": "写作表达", "score": 整数, "note": ""}},
    {{"label": "创新贡献", "score": 整数, "note": ""}}
  ],
  "literature": ["结合本文具体主题应补充的文献方向（写到具体主题词，不要泛泛说'经典理论'），3-4条"],
  "journals": [{{"level": "投稿层级名称", "note": "结合本文当前完成度说明差距与努力方向，2-3个层级"}}],
  "logic_chain": "1-2句判断：绪论提出的研究问题在后文是否得到回应、结论是否呼应研究目标、有无明显逻辑跳跃或断裂，必须点到本文具体章节/论点",
  "ai_risk": "低|中|高 之一",
  "ai_risk_note": "若中/高，具体指出本文哪些段落有 AI 痕迹（空泛肯定无数据、高频套话连接词、过于工整并列、空洞黑话）；若低，一句话说明依据"
}}
评分要客观区分：结构残缺的初稿不应超过 65 分；完整且方法清楚的课程论文 70-82；达到投稿初稿水平再给 83+。只输出 JSON。"""
        raw = self._call_llm(prompt, temperature=0.4, max_tokens=6144)
        parsed = self._parse_json_safe(raw)
        if not isinstance(parsed, dict):
            parsed = {}
        parsed.setdefault("document_type", doc_type_hint or "课程论文")
        return parsed

    # ------------------------------------------------------------------
    # 修改清单 + 风险 + 改写示例（一次调用，基于已定位的证据）
    # ------------------------------------------------------------------
    def _action_review(self, title: str, manuscript: str, annotations: List[Annotation]) -> Dict[str, List[Dict[str, Any]]]:
        evidence = "\n".join(
            f"{a.id}. [{a.severity}/{a.module_name}] 原文摘录：{a.quote[:60]}\n   问题：{a.issue[:120]}\n   建议：{a.suggestion[:120]}"
            for a in annotations
        )
        prompt = f"""下面是对文稿《{title}》逐段审查后确认的问题清单（均已定位到原文）：

{evidence}

文稿开头供参考：
{manuscript[:2500]}

请基于这些"已确认问题"产出三部分内容，不要重复制造新问题，不要写与上面重复的套话，输出 JSON：
{{
  "checklist": [
    {{"priority": "高|中|低", "category": "分类（如论证/文献/方法/格式/语言）", "action": "一句具体行动", "detail": "说明在稿件哪里改、怎么改（引用具体段落或表述）"}}
  ],
  "risks": [
    {{"risk_type": "风险类型", "severity": "高|中|低", "description": "结合本文内容的风险描述", "suggestion": "应对建议"}}
  ],
  "rewrites": [
    {{"section": "部分名称", "original": "必须从上文问题清单的原文摘录中选取", "rewritten": "学术化改写后的版本（保留原意）", "notes": "说明改了什么、为什么"}}
  ]
}}
checklist 控制在 5-8 条并按优先级排序；risks 0-4 条，没有实质风险可返回空数组；rewrites 选最典型的 2-3 处。只输出 JSON。"""
        raw = self._call_llm(prompt, temperature=0.45, max_tokens=6144)
        parsed = self._parse_json_safe(raw)
        if not isinstance(parsed, dict):
            return {"checklist": [], "risks": [], "rewrites": []}
        return {
            "checklist": parsed.get("checklist", []) if isinstance(parsed.get("checklist"), list) else [],
            "risks": parsed.get("risks", []) if isinstance(parsed.get("risks"), list) else [],
            "rewrites": parsed.get("rewrites", []) if isinstance(parsed.get("rewrites"), list) else [],
        }

    # ------------------------------------------------------------------
    # 可选模块（仅在用户勾选时调用）
    # ------------------------------------------------------------------
    def run_translation(self, text_to_translate: str, direction: str = "auto") -> Dict[str, Any]:
        has_chinese = bool(re.search(r'[一-鿿]', text_to_translate))
        has_english = bool(re.search(r'[a-zA-Z]{4,}', text_to_translate))
        if direction == "auto":
            if has_chinese and not has_english:
                direction = "cn2en"
            elif has_english and not has_chinese:
                direction = "en2cn"
            else:
                direction = "cn2en"
        if direction == "cn2en":
            prompt = f'请将以下中文学术文本翻译为地道的英文学术表达。保持政治学与公共管理学科的专业术语规范。只返回英文译文，不要任何解释：\n\n{text_to_translate[:3000]}'
        else:
            prompt = f'请将以下英文学术文本翻译为规范的中文学术表达。保持政治学与公共管理学科的专业术语规范。只返回中文译文，不要任何解释：\n\n{text_to_translate[:3000]}'
        result = self._call_llm(prompt, "你是一个专业的中英学术翻译。你只返回翻译后的文本，不添加任何说明、注释或JSON格式。", temperature=0.3)
        if result.startswith("{") or result.startswith("```"):
            result = self._parse_json_safe(result).get("translated", result)
        return {
            "original": text_to_translate[:2000],
            "translated": result.strip(),
            "direction": direction,
            "auto_detected": direction == "cn2en" and has_chinese,
        }

    def run_reviewer_suggestions(self, title: str, manuscript: str) -> Dict[str, Any]:
        prompt = f"""根据文稿的研究主题和方法，给出适合的审稿人研究方向（不得虚构具体教师姓名）。
题目：{title}
文稿：{manuscript[:2500]}
输出 JSON：{{"summary": "结合本文主题的说明", "items": ["具体研究方向（须与本文主题直接相关）"]}}，3-5条，只输出 JSON。"""
        result = self._call_llm(prompt, temperature=0.4)
        return self._parse_json_safe(result)

    def run_journal_comparison(self, title: str, manuscript: str, target_journal_text: str = "") -> Dict[str, Any]:
        target_info = f"\n目标期刊/往期文章片段：{target_journal_text[:1500]}" if target_journal_text else ""
        prompt = f"""比较文稿与目标期刊风格的差距，所有判断必须基于本文实际内容。
题目：{title}
文稿：{manuscript[:3000]}{target_info}
输出 JSON：{{"summary": "总体比较结论", "items": [["维度", "本文当前实际情况", "目标风格要求"]]}}，
维度包括题目、摘要、文献综述、方法、结论、篇幅，只输出 JSON。"""
        result = self._call_llm(prompt, temperature=0.4)
        return self._parse_json_safe(result)

    # ------------------------------------------------------------------
    # 离线兜底报告（无 API Key）
    # ------------------------------------------------------------------
    def _build_offline_annotations(self, paragraphs: List[str], stats: Dict[str, Any]) -> List[Annotation]:
        anns: List[Annotation] = []
        next_id = 1

        def add(module: str, severity: str, pidx: int, quote: str, issue: str, suggestion: str) -> None:
            nonlocal next_id
            anns.append(Annotation(
                id=next_id, module=module, module_name=MODULE_NAMES.get(module, module),
                severity=severity, paragraph=pidx, quote=quote[:120],
                quote_matched=True, issue=issue, suggestion=suggestion,
            ))
            next_id += 1

        def find_paragraph(pattern: str) -> int:
            rx = re.compile(pattern)
            for i, p in enumerate(paragraphs):
                if rx.search(p):
                    return i + 1
            return 1

        def first_sentence(pidx: int) -> str:
            p = paragraphs[pidx - 1] if 1 <= pidx <= len(paragraphs) else paragraphs[0]
            m = re.search(r"[^。！？；]{8,80}[。！？；]", p)
            return (m.group(0) if m else p[:60]).strip()

        if not stats["has_abstract"]:
            pidx = find_paragraph(r"(一[、.]\s*研究背景|引言|前言)")
            add("format", "严重", pidx, first_sentence(pidx),
                "全文未检测到摘要部分，投稿与课程论文通常要求在正文前给出 200-300 字摘要。",
                "在正文前补充摘要，按'研究问题—方法—发现—结论'四要素撰写。")
        if not stats["has_keywords"]:
            pidx = find_paragraph(r"(摘\s*要|Abstract)")
            add("format", "一般", pidx, first_sentence(pidx),
                "未检测到关键词，不利于文献检索与编目。",
                "在摘要后补充 3-5 个关键词，如研究对象、理论视角、方法与案例地。")
        if not stats["has_methods"]:
            pidx = max(find_paragraph(r"(研究思路|研究设计|分析框架)"), 1)
            add("data_methods", "严重", pidx, first_sentence(pidx),
                "未检测到明确的研究方法说明，读者无法判断结论如何得出。",
                "单设研究方法部分，交代数据来源、样本/案例选择依据与分析方法。")
        if stats["ref_count"] < 3:
            ref_pidx = find_paragraph(r"(参考文献)") if any(re.search(r"参考文献", p) for p in paragraphs) else len(paragraphs)
            q = first_sentence(ref_pidx)
            add("references", "一般", ref_pidx, q,
                f"正文仅检测到 {stats['ref_count']} 处 [n] 形式的引用标记，学术对话不足。",
                "在提出概念、引用数据和借鉴框架处补充规范引用，并在文末列出完整文献。")
        # 空泛套话句子定位
        cliche_re = re.compile(r"[^。！？；]{0,40}(具有重要(的)?(理论|现实)?意义|有力抓手|保驾护航|添砖加瓦|高度重视|深刻阐明)[^。！？；]{0,30}[。！？；]?")
        hit = 0
        for i, p in enumerate(paragraphs, 1):
            m = cliche_re.search(p)
            if m and hit < 3:
                add("language", "建议", i, m.group(0).strip() or first_sentence(i),
                    "该处为口号化、空泛表述，缺少可检验的学术信息。",
                    "替换为具体机制、数据或可验证的判断，说明'谁、通过什么、产生了什么效果'。")
                hit += 1
        if stats["chars"] < 1000:
            pidx = len(paragraphs)
            add("depth", "一般", pidx, first_sentence(pidx),
                f"全文仅约 {stats['chars']} 字，论证空间不足，难以展开文献对话与实证分析。",
                "课程论文建议不少于 3000 字，补充文献综述、方法过程与证据呈现。")
        return anns

    def _build_offline_report(self, title: str, manuscript: str, paragraphs: List[str], modules: List[str]) -> Dict[str, Any]:
        stats = self._offline_text_stats(manuscript)
        annotations = self._build_offline_annotations(paragraphs, stats)
        score = stats["score"]
        structure = []
        if stats["has_abstract"]: structure.append("摘要")
        if stats["has_keywords"]: structure.append("关键词")
        if stats["has_intro"]: structure.append("引言/背景")
        if stats["has_methods"]: structure.append("研究方法")
        if stats["has_conclusion"]: structure.append("结论/建议")
        missing = [p for p in ("摘要", "关键词", "研究方法", "结论") if p not in "".join(structure)]

        strengths, weaknesses = [], []
        if stats["has_methods"]: strengths.append("文稿包含研究方法描述")
        if stats["chars"] > 2000: strengths.append(f"文稿篇幅约 {stats['chars']} 字，具备展开基础")
        if stats["ref_count"] >= 3: strengths.append(f"包含 {stats['ref_count']} 处参考文献引用标记")
        if not strengths: strengths.append("文稿已提交，具备基本篇章结构")
        if not stats["has_abstract"]: weaknesses.append("缺少摘要部分")
        if not stats["has_keywords"]: weaknesses.append("缺少关键词")
        if not stats["has_methods"]: weaknesses.append("未检测到明确的研究方法说明")
        if stats["ref_count"] < 3: weaknesses.append("参考文献引用标记较少")

        depth_items = [
            {"label": "选题意义", "score": 75, "note": "离线模式未做深度评价，请配置 API Key 后获取基于原文的评分依据。"},
            {"label": "理论基础", "score": 60, "note": "建议明确理论视角并补充文献综述。"},
            {"label": "研究问题", "score": 65, "note": "建议在引言末尾明确提出 1-2 个研究问题。"},
            {"label": "研究方法", "score": 70 if stats["has_methods"] else 45, "note": "已检测到方法描述" if stats["has_methods"] else "未检测到研究方法部分。"},
            {"label": "论证逻辑", "score": 65, "note": "建议检查论点—论据—结论之间的对应关系。"},
            {"label": "实证与数据", "score": 60, "note": "建议明确数据来源与样本信息。"},
            {"label": "写作表达", "score": 70, "note": "注意避免空泛口号化表述。"},
            {"label": "创新贡献", "score": 60, "note": "建议在结论部分明确理论贡献与实践价值。"},
        ]
        module_results = self._assemble_module_results(modules, annotations, depth_items, [], [])
        return {
            "document_type": "课程论文",
            "overall": {
                "document_type": "课程论文",
                "completion_level": f"文稿共 {stats['chars']} 字，结构完整度：{'/'.join(structure) if structure else '待确认'}。{'缺少：' + '、'.join(missing) if missing else '基本结构较完整。'}（当前为离线基础检查，配置 API Key 后可获得逐段 AI 审稿。）",
                "overall_score": score,
                "strengths": strengths,
                "weaknesses": weaknesses,
                "priority": "在 .env 中配置 DASHSCOPE_API_KEY 或 OPENAI_API_KEY 后重新提交，获取逐段证据审稿。",
            },
            "annotations": annotations,
            "module_results": module_results,
            "checklist": [
                {"priority": "高", "category": "配置", "action": "配置 API Key", "detail": "在 city_research/.env 填入真实的 DASHSCOPE_API_KEY（阿里云百炼）或 OPENAI_API_KEY。"},
            ],
            "risks": [
                {"risk_type": "离线模式", "severity": "高", "description": "当前仅为规则检查，未启用 AI 逐段审稿。", "suggestion": "配置有效 API Key 后重新提交。"},
            ],
            "rewrites": [],
        }

    # ------------------------------------------------------------------
    # 模块结果组装（兼容雷达图 / 分项 tab）
    # ------------------------------------------------------------------
    def _assemble_module_results(
        self,
        modules: List[str],
        annotations: List[Annotation],
        depth_items: List[Dict[str, Any]],
        literature: List[Any],
        journals: List[Any],
        extra: Optional[Dict[str, ModuleResult]] = None,
    ) -> List[ModuleResult]:
        results: List[ModuleResult] = []
        for key in modules:
            if key == "depth":
                results.append(ModuleResult(
                    module_key=key, module_name=MODULE_NAMES[key],
                    summary="八维度评分（评分依据均来自原文）", items=depth_items,
                ))
            elif key in CORE_MODULES:
                group = [a for a in annotations if a.module == key]
                items = [{
                    "severity": a.severity,
                    "paragraph": a.paragraph,
                    "quote": a.quote,
                    "issue": a.issue,
                    "suggestion": a.suggestion,
                } for a in group]
                summary = f"发现 {len(group)} 处需要关注的问题，已在原文中逐条定位。" if group else "通读后未发现该维度的明显问题。"
                results.append(ModuleResult(
                    module_key=key, module_name=MODULE_NAMES[key], summary=summary, items=items,
                ))
            elif key == "literature":
                items = [{"content": str(x)} for x in literature] if literature and not isinstance(literature[0], dict) else literature
                results.append(ModuleResult(
                    module_key=key, module_name=MODULE_NAMES[key],
                    summary="结合本文主题建议补充的文献方向（具体文献请自行核验）", items=items,
                ))
            elif key == "journals":
                results.append(ModuleResult(
                    module_key=key, module_name=MODULE_NAMES[key],
                    summary="投稿层级建议（仅供参考，不代表录用承诺）", items=journals,
                ))
            elif extra and key in extra:
                results.append(extra[key])
        return results

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    def run_full_review(self, title: str, manuscript: str, modules: Optional[List[str]] = None) -> PreReviewResponse:
        request_id = str(uuid.uuid4())
        raw_text = manuscript
        paragraphs = self._split_paragraphs(manuscript)

        if modules is None:
            modules = ["references", "depth", "language", "format", "data_methods", "literature", "journals"]

        if not self.llm_available:
            offline = self._build_offline_report(title, manuscript, paragraphs, modules)
            response = PreReviewResponse(
                request_id=request_id,
                title=title,
                document_type=offline["document_type"],
                raw_text=raw_text,
                paragraphs=paragraphs,
                overall_assessment=OverallAssessment(**offline["overall"]),
                main_issues=[MainIssue(severity=a.severity, description=a.issue, reason=f"原文：{a.quote}；建议：{a.suggestion}") for a in offline["annotations"][:6]],
                annotations=offline["annotations"],
                module_results=offline["module_results"],
                modification_checklist=[ChecklistItem(**c) for c in offline["checklist"]],
                risk_warnings=[RiskWarning(**r) for r in offline["risks"]],
                rewrite_examples=[],
                created_at=datetime.now().isoformat(),
            )
            self.review_cache[request_id] = response.model_dump()
            return response

        # ---- LLM 完整流程 ----
        doc_type_hint = "课程论文"

        # 1) 逐段证据审稿（按字数分批，覆盖全文）
        raw_annotations: List[Dict[str, Any]] = []
        total_chars = sum(len(p) for p in paragraphs)
        char_budget = 7000
        # 超长稿件（整份学位论文 / OCR 全文）限制逐段审稿批次数，给串行 LLM
        # 调用的总时长与资源占用设上界，避免超长文本把请求拖到数十分钟。
        max_batches = max(1, int(os.getenv("PRE_REVIEW_MAX_BATCHES", "16")))
        if total_chars <= char_budget:
            batches = [(0, len(paragraphs))]
        else:
            batches = []
            start = 0
            while start < len(paragraphs) and len(batches) < max_batches:
                end, _ = self._build_numbered_block(paragraphs, start, len(paragraphs), char_budget)
                if end <= start:
                    end = start + 1
                batches.append((start, end))
                start = end
            if start < len(paragraphs):
                LOGGER.info(
                    "PreReview %s: capped at %d review batches, paragraphs %d/%d covered",
                    request_id, max_batches, start, len(paragraphs),
                )
        LOGGER.info("PreReview %s: %d paragraphs, %d review batches", request_id, len(paragraphs), len(batches))
        for bi, (s, e) in enumerate(batches, 1):
            try:
                raw_annotations.extend(self._evidence_review_batch(title, doc_type_hint, paragraphs, s, e))
            except Exception as exc:
                LOGGER.error("Evidence review batch %d failed: %s", bi, exc)

        annotations = self._validate_annotations(raw_annotations, paragraphs)
        if not annotations:
            # 在线证据审稿意外为空（模型输出异常或截断无法恢复）时，用规则结果兜底，
            # 保证任何情况下页面都有可在原文定位的意见
            LOGGER.warning(
                "PreReview %s: online evidence empty (raw_items=%d), rule fallback", request_id, len(raw_annotations)
            )
            stats = self._offline_text_stats(manuscript)
            annotations = self._build_offline_annotations(paragraphs, stats)

        # 2) 总体评价 + 评分 + 文献/期刊建议
        try:
            overall_raw = self._overall_review(title, manuscript, doc_type_hint, annotations)
        except Exception as exc:
            LOGGER.error("Overall review failed: %s", exc)
            overall_raw = {}
        doc_type = str(overall_raw.get("document_type", "课程论文")).strip() or "课程论文"
        depth_items = []
        for it in overall_raw.get("scores", []):
            if isinstance(it, dict) and it.get("label") is not None:
                try:
                    score = int(it.get("score", 0))
                except (TypeError, ValueError):
                    score = 0
                depth_items.append({"label": str(it.get("label", "")), "score": max(0, min(100, score)), "note": str(it.get("note", ""))})
        if not depth_items:
            depth_items = [{"label": k, "score": 70, "note": "评分生成失败，请重试。"} for k in
                           ("选题意义", "理论基础", "研究问题", "研究方法", "论证逻辑", "实证与数据", "写作表达", "创新贡献")]
        literature = overall_raw.get("literature", [])
        journals_raw = overall_raw.get("journals", [])
        journals = journals_raw if isinstance(journals_raw, list) else []

        overall = OverallAssessment(
            document_type=doc_type,
            completion_level=str(overall_raw.get("completion_level", "")),
            overall_score=int(overall_raw.get("overall_score", 70) or 70),
            strengths=[str(x) for x in overall_raw.get("strengths", []) if x],
            weaknesses=[str(x) for x in overall_raw.get("weaknesses", []) if x],
            priority=str(overall_raw.get("priority", "")),
        )

        # 3) 修改清单 + 风险 + 改写示例
        try:
            action = self._action_review(title, manuscript, annotations)
        except Exception as exc:
            LOGGER.error("Action review failed: %s", exc)
            action = {"checklist": [], "risks": [], "rewrites": []}
        checklist = [ChecklistItem(
            priority=str(c.get("priority", "")), category=str(c.get("category", "")),
            action=str(c.get("action", "")), detail=str(c.get("detail", "")),
        ) for c in action["checklist"] if isinstance(c, dict)]
        risks = [RiskWarning(
            risk_type=str(r.get("risk_type", "")), severity=str(r.get("severity", "")),
            description=str(r.get("description", "")), suggestion=str(r.get("suggestion", "")),
        ) for r in action["risks"] if isinstance(r, dict)]
        rewrites = [RewriteExample(
            section=str(e.get("section", "")), original=str(e.get("original", "")),
            rewritten=str(e.get("rewritten", "")), notes=str(e.get("notes", "")),
        ) for e in action["rewrites"] if isinstance(e, dict)]

        # 4) 可选模块（仅勾选时调用）
        extra: Dict[str, ModuleResult] = {}
        if "reviewers" in modules:
            try:
                rv = self.run_reviewer_suggestions(title, manuscript)
                extra["reviewers"] = ModuleResult(
                    module_key="reviewers", module_name=MODULE_NAMES["reviewers"],
                    summary=str(rv.get("summary", "")), items=[{"content": str(x)} for x in rv.get("items", [])],
                )
            except Exception as exc:
                LOGGER.error("Reviewer suggestions failed: %s", exc)
        if "comparison" in modules:
            try:
                cmp_ = self.run_journal_comparison(title, manuscript, "")
                rows = cmp_.get("items", []) if isinstance(cmp_, dict) else []
                items = []
                for row in rows:
                    if isinstance(row, (list, tuple)) and len(row) >= 3:
                        items.append({"col0": str(row[0]), "col1": str(row[1]), "col2": str(row[2])})
                extra["comparison"] = ModuleResult(
                    module_key="comparison", module_name=MODULE_NAMES["comparison"],
                    summary=str(cmp_.get("summary", "") if isinstance(cmp_, dict) else ""), items=items,
                )
            except Exception as exc:
                LOGGER.error("Journal comparison failed: %s", exc)
        if "translation" in modules:
            try:
                tr = self.run_translation(f"{title}\n\n{manuscript[:3000]}", "auto")
                extra["translation"] = ModuleResult(
                    module_key="translation", module_name=MODULE_NAMES["translation"],
                    summary="翻译结果", items=[tr],
                )
            except Exception as exc:
                LOGGER.error("Translation failed: %s", exc)

        module_results = self._assemble_module_results(modules, annotations, depth_items, literature, journals, extra)

        # 主要问题：取严重/一般 annotation 映射，兼容旧字段
        main_issues = [
            MainIssue(
                severity=a.severity,
                description=a.issue,
                reason=f"原文摘录（第{a.paragraph}段）：{a.quote}；修改建议：{a.suggestion}",
            )
            for a in annotations if a.severity in ("严重", "一般")
        ][:8]

        response = PreReviewResponse(
            request_id=request_id,
            title=title,
            document_type=doc_type,
            raw_text=raw_text,
            paragraphs=paragraphs,
            overall_assessment=overall,
            main_issues=main_issues,
            annotations=annotations,
            module_results=module_results,
            modification_checklist=checklist,
            risk_warnings=risks,
            rewrite_examples=rewrites,
            created_at=datetime.now().isoformat(),
        )
        self.review_cache[request_id] = response.model_dump()
        return response


pre_review_service = PreReviewService()
