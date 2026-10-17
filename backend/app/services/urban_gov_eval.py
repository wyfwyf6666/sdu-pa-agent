from __future__ import annotations

import csv
import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from statistics import mean
from typing import Any, Dict, Iterable, List, Optional, Protocol, Tuple
from urllib.parse import parse_qs, quote, unquote, urlparse

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - fallback when SDK 未安装
    OpenAI = None  # type: ignore

# 引入评测中使用的数据模型定义，便于统一封装评测结果结构
from backend.app.models.eval import (
    ConfidenceInterval,
    CriterionScore,
    DomainScore,
    EvaluationCriterion,
    FactExpectation,
    FactMetrics,
    FactPairResult,
    RaceDimensionScore,
    RaceResult,
    TaskMetricDefinition,
    TaskMetricScore,
    UrbanGovEvalPerTaskResult,
    UrbanGovEvalSummary,
    UrbanGovEvalTask,
)

logger = logging.getLogger(__name__)

DEFAULT_OPENAI_API_KEY = ""
DEFAULT_OPENAI_BASE_URL = ""
_DEFAULT_OPENAI_CLIENT: Optional[Any] = None


# 将数值限制在指定区间，避免评测过程中出现异常的极端值
def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9]+", text or "")


def _sentence_split(text: str) -> List[str]:
    return [
        seg.strip()
        for seg in re.split(r"[。！？!?\\n]+", text or "")
        if seg and seg.strip()
    ]


DOMAIN_KEYWORD_HINTS: Dict[str, List[str]] = {
    "城市更新": ["城市更新", "老旧", "改造", "更新"],
    "公共安全": ["公共安全", "应急", "消防", "联动", "演练"],
    "数字治理": ["数字治理", "12345", "热线", "数字", "政务"],
    "城市交通": ["交通", "地铁", "轨道", "出行"],
    "医疗保障": ["医疗", "医保", "就医", "保障"],
    "环境治理": ["环境", "水体", "黑臭", "生态", "污染"],
    "社会治理": ["社会治理", "社区", "群租", "居民"],
    "营商环境": ["营商", "招商", "园区", "企业", "审批"],
}


def _overlap_ratio(source_tokens: List[str], target_tokens: List[str]) -> float:
    if not source_tokens:
        return 0.0
    source_set = set(source_tokens)
    target_set = set(target_tokens)
    return len(source_set & target_set) / len(source_set)


def _rouge_l(tokens_a: List[str], tokens_b: List[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    len_b = len(tokens_b)
    dp = [0] * (len_b + 1)
    for token_a in tokens_a:
        prev = 0
        for idx, token_b in enumerate(tokens_b, start=1):
            temp = dp[idx]
            if token_a == token_b:
                dp[idx] = prev + 1
            else:
                dp[idx] = max(dp[idx], dp[idx - 1])
            prev = temp
    lcs = dp[-1]
    precision = lcs / len(tokens_a)
    recall = lcs / len(tokens_b)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _jaccard(tokens_a: List[str], tokens_b: List[str]) -> float:
    if not tokens_a or not tokens_b:
        return 0.0
    set_a = set(tokens_a)
    set_b = set(tokens_b)
    union = set_a | set_b
    if not union:
        return 0.0
    return len(set_a & set_b) / len(union)


def _contains_keywords(text: str, keywords: List[str]) -> int:
    if not text:
        return 0
    return sum(text.count(keyword) for keyword in keywords)


def _has_time_marker(text: str) -> bool:
    return bool(re.search(r"(20\d{2}|本年|今年|季度|月份|月|周|近期)", text or ""))


POLICY_KEYWORDS = [
    "政策",
    "条例",
    "规划",
    "机制",
    "指标",
    "执行",
    "问责",
    "协同",
    "部门",
    "监管",
]

STRUCTURE_PATTERNS = re.compile(r"^\s*(?:\d+[\.\)]|[（(][一二三四五六][）)]|[-•])", re.MULTILINE)


@dataclass
class TaskPayload:
    task_id: str
    prompt_messages: List[Dict[str, str]]
    reference_answer: str


class AnswerModelProtocol(Protocol):
    def generate(self, messages: List[Dict[str, str]]) -> str: ...


class JudgeModelProtocol(Protocol):
    def score(
        self,
        *,
        task: UrbanGovEvalTask,
        candidate: str,
        reference: str,
        query: str,
    ) -> Dict[str, Dict[str, Any]]:
        ...


def _create_openai_client(api_key: str, base_url: Optional[str]) -> Any:
    if OpenAI is None:
        raise RuntimeError("未安装 openai SDK，无法创建 GPT 客户端")
    return OpenAI(api_key=api_key, base_url=base_url or DEFAULT_OPENAI_BASE_URL)


def _get_default_openai_client() -> Any:
    global _DEFAULT_OPENAI_CLIENT
    if _DEFAULT_OPENAI_CLIENT is None:
        _DEFAULT_OPENAI_CLIENT = _create_openai_client(DEFAULT_OPENAI_API_KEY, DEFAULT_OPENAI_BASE_URL)
    return _DEFAULT_OPENAI_CLIENT


def _strip_code_fence(payload: str) -> str:
    text = payload.strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 3:
            return parts[1].strip() if parts[1].strip() else parts[2].strip()
        return text.strip("`")
    return text


def _try_parse_json_object(payload: str) -> Optional[Dict[str, Any]]:
    """
    尝试从模型返回文本中提取 JSON 对象。
    先直接解析，失败后再提取首尾花括号之间的片段进行兜底解析。
    """
    text = payload.strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        snippet = text[start : end + 1].strip()
        try:
            parsed = json.loads(snippet)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
    return None


class TemplateAnswerModel:
    """默认回答模型：基于问题提纲生成结构化占位答案."""

    def generate(self, messages: List[Dict[str, str]]) -> str:
        user_prompt = ""
        for message in reversed(messages):
            if message.get("role") == "user":
                user_prompt = message.get("content", "").strip()
                break
        if not user_prompt and messages:
            user_prompt = messages[-1].get("content", "").strip()

        points = _sentence_split(user_prompt)[:3]
        bullets = "\n".join(
            f"{idx}. 聚焦“{point[:18]}”的问题，提出可执行举措。" for idx, point in enumerate(points, start=1)
        )
        if not bullets:
            bullets = "1. 结合政策要求给出治理方向。\n2. 补充实施抓手与配套条件。\n3. 给出风险与监测建议。"

        return (
            f"【占位回答】针对“{user_prompt[:60]}”这一治理议题，给出临时评估框架：\n"
            f"一、问题诊断：概括现状痛点、涉众与约束条件，明确指标缺口。\n"
            f"二、策略建议：\n{bullets}\n"
            f"三、配套机制：同步设计考核、数据共享与联动协同流程。\n"
            f"四、风险提示：识别资源、舆情与执行风险，并提供监测阈值。"
        )


class KeywordJudgeModel:
    """默认判分模型：基于文本重合度与结构特征给出评分."""

    def score(
        self,
        *,
        task: UrbanGovEvalTask,
        candidate: str,
        reference: str,
        query: str,
    ) -> Dict[str, Dict[str, Any]]:
        candidate_tokens = _tokenize(candidate)
        reference_tokens = _tokenize(reference)
        query_tokens = _tokenize(query)

        coverage_ratio = _overlap_ratio(query_tokens, candidate_tokens)
        depth_ratio = _overlap_ratio(reference_tokens, candidate_tokens)
        compliance_hits = _contains_keywords(candidate, POLICY_KEYWORDS)
        paragraphs = [seg for seg in candidate.split("\n") if seg.strip()]
        structure_hits = len(STRUCTURE_PATTERNS.findall(candidate))
        structure_ratio = min(1.0, (len(paragraphs) / 4.0) + (structure_hits / 6.0))

        results: Dict[str, Dict[str, Any]] = {}
        for criterion in task.criteria:
            dimension = criterion.dimension
            if dimension == "coverage":
                score = 3.0 + coverage_ratio * 7.0
                explanation = f"覆盖率约为 {coverage_ratio * 100:.1f}%，能回应主要问题要素。"
            elif dimension == "depth":
                score = 2.5 + depth_ratio * 7.5
                explanation = f"与参考答案内容重合度 {depth_ratio * 100:.1f}%，体现一定诊断深度。"
            elif dimension == "compliance":
                score = 2.0 + min(6.0, compliance_hits * 1.0) + coverage_ratio * 2.0
                explanation = f"命中政策关键词 {compliance_hits} 次，表述具备一定合规依据。"
            elif dimension == "readability":
                score = 3.5 + structure_ratio * 6.5
                explanation = (
                    f"输出包含 {len(paragraphs)} 个段落 / {structure_hits} 个列点，结构度量 {structure_ratio * 100:.1f}%。"
                )
            else:
                score = 3.0 + depth_ratio * 6.0
                explanation = f"参考通用指标，内容相似度 {depth_ratio * 100:.1f}%。"

            results[criterion.id] = {
                "score": float(round(_clamp(score, 0.0, 10.0), 2)),
                "explanation": explanation,
            }
        return results


class GPTAnswerModel:
    """通过 GPT-4o 系列模型生成候选答案."""

    def __init__(
        self,
        client: Optional[Any] = None,
        *,
        model: str = "gpt-4o",
        temperature: float = 0.4,
        top_p: float = 0.9,
        max_tokens: int = 900,
        system_prompt: Optional[str] = None,
    ) -> None:
        if client is None:
            client = _get_default_openai_client()
        self.client: Any = client
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt

    def generate(self, messages: List[Dict[str, str]]) -> str:
        payload = list(messages)
        if self.system_prompt:
            payload = [{"role": "system", "content": self.system_prompt}] + payload
        elif not payload or payload[0].get("role") != "user":
            last_user = ""
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    last_user = msg.get("content", "")
                    break
            payload = [{"role": "user", "content": last_user or ""}]
        response = self.client.chat.completions.create(
            model=self.model,
            messages=payload,
            temperature=self.temperature,
            top_p=self.top_p,
            max_tokens=self.max_tokens,
        )
        return (response.choices[0].message.content or "").strip()


class GPTJudgeModel:
    """通过 GPT-4o 系列模型执行 Criterion 打分."""

    def __init__(
        self,
        client: Optional[Any] = None,
        *,
        model: str = "gpt-4o",
        temperature: float = 0.0,
        top_p: float = 0.9,
        max_tokens: int = 900,
        system_prompt: str = (
            "你是专业的政务评测官，需对候选回答按照标准 0-10 分打分，输出 JSON，确保客观一致。"
        ),
        fallback: Optional[JudgeModelProtocol] = None,
    ) -> None:
        if client is None:
            client = _get_default_openai_client()
        self.client: Any = client
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.system_prompt = system_prompt
        self.fallback = fallback or KeywordJudgeModel()

    def score(
        self,
        *,
        task: UrbanGovEvalTask,
        candidate: str,
        reference: str,
        query: str,
    ) -> Dict[str, Dict[str, Any]]:
        criteria_payload = [
            {
                "id": item.id,
                "name": item.name,
                "dimension": item.dimension,
                "description": item.description,
                "weight": item.weight,
                "reference_score": item.reference_score,
            }
            for item in task.criteria
        ]
        judge_prompt = (
            f"题目编号：{task.task_id}\n"
            f"题目名称：{task.title}\n"
            f"用户问题：{query}\n\n"
            f"参考答案：\n{reference}\n\n"
            f"候选答案：\n{candidate}\n\n"
            f"评分标准（JSON 数组）：\n{json.dumps(criteria_payload, ensure_ascii=False, indent=2)}\n\n"
            "请针对每个标准给出 0-10 的得分与一句中文解释，输出 JSON，对应键为标准 id，格式：\n"
            '{"C1":{"score":8.2,"explanation":"..."},"C2":{"score":7.5,"explanation":"..."}}\n'
            "只允许输出 JSON，不要额外说明。"
        )
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": judge_prompt},
        ]
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                top_p=self.top_p,
                max_tokens=self.max_tokens,
            )
            content = (response.choices[0].message.content or "").strip()
            content = _strip_code_fence(content)
            scores = _try_parse_json_object(content)
            if scores is None:
                raise ValueError("GPT 返回内容无法解析为 JSON")
            return {
                key: {
                    "score": float(value.get("score", 0)),
                    "explanation": str(value.get("explanation", "")).strip(),
                }
                for key, value in scores.items()
                if isinstance(value, dict)
            }
        except Exception as exc:  # pragma: no cover - 网络/解析错误走回退
            return self.fallback.score(
                task=task,
                candidate=candidate,
                reference=reference,
                query=query,
            )


class UrbanGovEvalService:
    """UrbanGovEval 全流程管控."""

    def __init__(self) -> None:
        # 预置评测所需的目录结构，统一管理原始数据、参考数据与输出结果
        self.base_dir = Path(__file__).resolve().parents[2] / "data" / "urban_gov_eval"
        self.repo_root = Path(__file__).resolve().parents[3]
        self.reference_dir = self.base_dir / "reference"
        self.per_task_dir = self.base_dir / "per_task"
        self.raw_dir = self.base_dir / "raw_data"
        self.summary_dir = self.base_dir / "summary"
        self.question_bank_file = self.base_dir / "query.jsonl"
        self.documents_dir = self.repo_root / "backend" / "data" / "public" / "documents"
        self.public_metadata_file = self.repo_root / "backend" / "data" / "public" / "metadata.json"
        self.private_metadata_file = self.repo_root / "backend" / "data" / "private" / "metadata.json"
        self._tasks_cache: List[UrbanGovEvalTask] = []
        self._tasks_mtime: float = 0.0
        self._task_payloads: Dict[str, TaskPayload] = {}
        self._knowledge_docs: List[str] = []
        self._knowledge_docs_mtime: float = 0.0
        self._knowledge_docs = self._load_knowledge_docs()
        self._document_meta: Dict[str, Dict[str, Any]] = {}
        self._document_meta_mtime: Tuple[float, float] = (0.0, 0.0)
        self.default_task_limit = 24  # 默认每轮只抽取少量题目
        self.answer_model: AnswerModelProtocol = TemplateAnswerModel()
        self.judge_model: JudgeModelProtocol = KeywordJudgeModel()
        self._ensure_dirs()
        self._maybe_bootstrap_remote_models()

    def _ensure_dirs(self) -> None:
        # 避免评测时因路径缺失导致写入失败
        for path in [
            self.base_dir,
            self.reference_dir,
            self.per_task_dir,
            self.raw_dir,
            self.summary_dir,
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def _load_knowledge_docs(self) -> List[str]:
        if not self.documents_dir.exists():
            self._knowledge_docs_mtime = 0.0
            return []
        try:
            mtime = self.documents_dir.stat().st_mtime
        except FileNotFoundError:
            self._knowledge_docs_mtime = 0.0
            return []
        files = [
            item.name
            for item in sorted(self.documents_dir.iterdir(), key=lambda p: p.name)
            if item.is_file()
        ]
        self._knowledge_docs_mtime = mtime
        return files

    def _refresh_knowledge_docs_if_needed(self) -> None:
        try:
            current_mtime = self.documents_dir.stat().st_mtime
        except FileNotFoundError:
            current_mtime = 0.0
        if not self._knowledge_docs or current_mtime != self._knowledge_docs_mtime:
            self._knowledge_docs = self._load_knowledge_docs()

    def _filter_docs_by_domain(self, domain: Optional[str]) -> List[str]:
        self._refresh_knowledge_docs_if_needed()
        docs = self._knowledge_docs
        if not docs or not domain:
            return docs
        keywords = DOMAIN_KEYWORD_HINTS.get(domain, [domain])
        filtered = [name for name in docs if any(keyword in name for keyword in keywords)]
        return filtered or docs

    def _pick_knowledge_doc(self, index: int, domain: Optional[str] = None) -> Optional[str]:
        docs = self._filter_docs_by_domain(domain)
        if not docs:
            return None
        return docs[index % len(docs)]

    def _build_doc_download_url(self, filename: str) -> str:
        return f"/api/v1/documents/download?filename={quote(filename)}"

    def _knowledge_doc_exists(self, filename: str) -> bool:
        if not filename:
            return False
        path = self.documents_dir / filename
        return path.exists()

    def _load_document_metadata(self) -> Dict[str, Dict[str, Any]]:
        meta: Dict[str, Dict[str, Any]] = {}
        files = [self.public_metadata_file, self.private_metadata_file]
        for file in files:
            if not file.exists():
                continue
            try:
                with file.open("r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                continue
            documents = data.get("documents")
            if not documents and isinstance(data, dict):
                documents = {k: v for k, v in data.items() if isinstance(v, dict)}
            if isinstance(documents, dict):
                for name, info in documents.items():
                    meta[name] = info
        public_mtime = self.public_metadata_file.stat().st_mtime if self.public_metadata_file.exists() else 0.0
        private_mtime = (
            self.private_metadata_file.stat().st_mtime if self.private_metadata_file.exists() else 0.0
        )
        self._document_meta_mtime = (public_mtime, private_mtime)
        return meta

    def _refresh_document_metadata_if_needed(self) -> None:
        public_mtime = self.public_metadata_file.stat().st_mtime if self.public_metadata_file.exists() else 0.0
        private_mtime = (
            self.private_metadata_file.stat().st_mtime if self.private_metadata_file.exists() else 0.0
        )
        if (
            not self._document_meta
            or self._document_meta_mtime != (public_mtime, private_mtime)
        ):
            self._document_meta = self._load_document_metadata()

    def _get_document_meta(self, filename: str) -> Optional[Dict[str, Any]]:
        if not filename:
            return None
        self._refresh_document_metadata_if_needed()
        return self._document_meta.get(filename)

    def _infer_authority_from_doc(self, filename: str, meta: Optional[Dict[str, Any]]) -> bool:
        policy_keywords = [
            "国务院",
            "政府",
            "通知",
            "意见",
            "条例",
            "法律",
            "法",
            "方案",
            "批复",
            "规定",
            "指导",
            "规划",
            "实施",
            "办法",
            "标准",
            "条例",
        ]
        if meta:
            category = meta.get("category")
            tags = meta.get("tags") or []
            doc_type = meta.get("document_type")
            if category in {"政策", "法规", "政府公告", "批复", "规章"}:
                return True
            if doc_type and any(key in doc_type for key in policy_keywords):
                return True
            if any(key in (category or "") for key in policy_keywords):
                return True
            if any(any(key in str(tag) for key in policy_keywords) for tag in tags):
                return True
        return any(keyword in filename for keyword in policy_keywords)

    def _parse_year_from_string(self, text: str) -> Optional[int]:
        match = re.search(r"(20\d{2})", text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
        return None

    def _infer_timeliness_from_doc(self, filename: str, meta: Optional[Dict[str, Any]]) -> bool:
        now = datetime.utcnow()
        threshold = now - timedelta(days=365 * 4)
        time_fields = []
        if meta:
            for key in ["updated_time", "upload_time"]:
                value = meta.get(key)
                if value:
                    time_fields.append(value)
        for value in time_fields:
            try:
                ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
                if ts >= threshold:
                    return True
            except Exception:
                continue
        year = self._parse_year_from_string(filename)
        if year and year >= (now.year - 4):
            return True
        return False

    def _extract_filename_from_citation(self, citation: str) -> Optional[str]:
        if not citation:
            return None
        try:
            parsed = urlparse(citation)
        except Exception:
            parsed = None
        if parsed and parsed.query:
            params = parse_qs(parsed.query)
            filename = params.get("filename", [None])[0]
            if filename:
                return unquote(filename)
        if "/documents/" in citation:
            parts = citation.split("/documents/", 1)[-1].split("/")
            if parts:
                target = parts[0]
                if target:
                    return unquote(target)
        return None

    def _ensure_fact_pairs_have_docs(
        self,
        result: UrbanGovEvalPerTaskResult,
        save_if_changed: bool = False,
    ) -> None:
        domain = result.metadata.get("domain") if isinstance(result.metadata, dict) else None
        updated = False
        for idx, pair in enumerate(result.fact.pairs):
            filename = self._extract_filename_from_citation(pair.citation)
            if filename and self._knowledge_doc_exists(filename):
                meta = self._get_document_meta(filename)
                if pair.support:
                    pair.authority = self._infer_authority_from_doc(filename, meta)
                    pair.timeliness = self._infer_timeliness_from_doc(filename, meta)
                continue
            doc_name = self._pick_knowledge_doc(idx, domain=domain)
            if not doc_name:
                continue
            pair.citation = self._build_doc_download_url(doc_name)
            pair.normalized_citation = doc_name
            note = pair.notes or ""
            doc_note = f"知识库引用《{doc_name}》"
            if doc_note not in note:
                pair.notes = f"{note}；{doc_note}" if note else doc_note
            meta = self._get_document_meta(doc_name)
            if pair.support:
                pair.authority = self._infer_authority_from_doc(doc_name, meta)
                pair.timeliness = self._infer_timeliness_from_doc(doc_name, meta)
            updated = True
        if updated:
            fact = result.fact
            fact.authoritative_pairs = sum(1 for p in fact.pairs if p.authority)
            fact.timely_pairs = sum(1 for p in fact.pairs if p.timeliness)
            fact.misuse_pairs = sum(1 for p in fact.pairs if p.misuse)
            fact.supported_pairs = sum(1 for p in fact.pairs if p.support)
            total = len(fact.pairs) or 1
            supported = fact.supported_pairs or 0
            fact.citation_accuracy = float(round((supported / total) * 100, 2))
            fact.effective_citations = supported
            fact.source_authority_ratio = float(
                round((fact.authoritative_pairs / supported) * 100, 2) if supported else 0.0
            )
            fact.timeliness_ratio = float(
                round((fact.timely_pairs / supported) * 100, 2) if supported else 0.0
            )
            fact.misuse_rate = float(round((fact.misuse_pairs / total) * 100, 2))
            if save_if_changed:
                self._save_per_task(result)


    def _maybe_bootstrap_remote_models(self) -> None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.info("未检测到 OPENAI_API_KEY.")
            return
        base_url = os.environ.get("OPENAI_BASE_URL", "")
        answer_model_name = os.environ.get("URBAN_GOV_ANSWER_MODEL", "gpt-4o")
        judge_model_name = os.environ.get("URBAN_GOV_JUDGE_MODEL", "gpt-4o")
        try:
            client = _create_openai_client(api_key, base_url)
            answer_model = GPTAnswerModel(
                client=client,
                model=answer_model_name,
            )
            judge_model = GPTJudgeModel(
                client=client,
                model=judge_model_name,
                fallback=KeywordJudgeModel(),
            )
            self.configure_models(answer_model=answer_model, judge_model=judge_model)

        except Exception as exc:
            logger.warning("初始化模型失败，继续使用内置占位实现：%s", exc)

    def _load_tasks(self, force: bool = False) -> List[UrbanGovEvalTask]:
        if not self.question_bank_file.exists():
            raise FileNotFoundError(
                "未找到 query.jsonl，请确认题库已放置在 backend/data/urban_gov_eval/ 目录。"
            )

        mtime = self.question_bank_file.stat().st_mtime
        if not force and self._tasks_cache and self._tasks_mtime == mtime:
            return self._tasks_cache

        tasks = self._build_tasks_from_general_bank()
        self._tasks_cache = tasks
        self._tasks_mtime = mtime
        return tasks

    def _build_tasks_from_general_bank(self) -> List[UrbanGovEvalTask]:
        with self.question_bank_file.open("r", encoding="utf-8") as fh:
            raw_items = json.load(fh)

        tasks: List[UrbanGovEvalTask] = []
        payloads: Dict[str, TaskPayload] = {}

        for idx, item in enumerate(raw_items, start=1):
            messages = item.get("messages", [])
            if not messages:
                continue
            prompt_messages: List[Dict[str, str]] = [
                msg for msg in messages if msg.get("role") != "assistant"
            ]
            reference_answer = ""
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
                    reference_answer = msg.get("content", "").strip()
                    break
            if not prompt_messages:
                continue

            user_prompt = ""
            for msg in reversed(prompt_messages):
                if msg.get("role") == "user":
                    user_prompt = msg.get("content", "").strip()
                    break
            if not user_prompt:
                continue

            task_id = f"GEN-{idx:04d}"
            language = "zh" if re.search(r"[\u4e00-\u9fff]", user_prompt) else "en"
            difficulty = self._estimate_difficulty(user_prompt)
            task = UrbanGovEvalTask(
                task_id=task_id,
                title=self._derive_title(user_prompt),
                domain="通用治理",
                task_type="general_qa",
                language=language,
                difficulty=difficulty,
                time_ref="N/A",
                query=user_prompt,
                deliverable="围绕治理议题生成结构化建议，包含诊断、策略与配套保障。",
                output_format="三级标题 + 列点说明 + 风险提示",
                reference_report="query.jsonl",
                criteria=self._default_criteria(),
                fact_expectation=self._default_fact_expectation(),
                task_metrics=self._default_task_metrics(),
            )

            payloads[task_id] = TaskPayload(
                task_id=task_id,
                prompt_messages=prompt_messages,
                reference_answer=reference_answer,
            )
            tasks.append(task)

        self._task_payloads = payloads
        return tasks

    def configure_models(
        self,
        *,
        answer_model: Optional[AnswerModelProtocol] = None,
        judge_model: Optional[JudgeModelProtocol] = None,
    ) -> None:
        """允许外部在运行时注入真实的回答模型和判分模型实例."""
        if answer_model is not None:
            self.answer_model = answer_model
        if judge_model is not None:
            self.judge_model = judge_model

    def _derive_title(self, user_prompt: str) -> str:
        snippet = user_prompt.strip().replace("\n", " ")
        return snippet[:25] + ("..." if len(snippet) > 25 else "")

    def _estimate_difficulty(self, user_prompt: str) -> str:
        length = len(user_prompt)
        if length > 160:
            return "hard"
        if length > 90:
            return "medium"
        return "easy"

    def _default_criteria(self) -> List[EvaluationCriterion]:
        presets = [
            {
                "id": "C1",
                "name": "问题契合度",
                "description": "是否准确回应题目的核心矛盾与对象",
                "dimension": "coverage",
                "weight": 0.26,
                "reference_score": 8.2,
                "reference_comment": "参考答案完整覆盖提问要素",
            },
            {
                "id": "C2",
                "name": "诊断与分析",
                "description": "是否结合依据给出深度诊断与原因拆解",
                "dimension": "depth",
                "weight": 0.26,
                "reference_score": 8.5,
                "reference_comment": "参考答案以数据/案例支撑判断",
            },
            {
                "id": "C3",
                "name": "政策遵循",
                "description": "是否引用政策条款、合规边界与实施主体",
                "dimension": "compliance",
                "weight": 0.24,
                "reference_score": 8.3,
                "reference_comment": "参考答案列出政策依据与主体分工",
            },
            {
                "id": "C4",
                "name": "结构可读",
                "description": "是否提供决策友好的结构化表达和摘要",
                "dimension": "readability",
                "weight": 0.24,
                "reference_score": 8.0,
                "reference_comment": "参考答案采用摘要+条列+建议格式",
            },
        ]
        return [EvaluationCriterion(**preset) for preset in presets]

    def _default_fact_expectation(self) -> FactExpectation:
        return FactExpectation(
            expected_pairs=5,
            min_authority_ratio=0.55,
            min_timeliness_ratio=0.6,
        )

    def _default_task_metrics(self) -> List[TaskMetricDefinition]:
        return [
            TaskMetricDefinition(
                metric="Rouge-L",
                description="候选与参考答案的最长公共子序列 F1",
                reference_value=0.72,
            ),
            TaskMetricDefinition(
                metric="TokenOverlap",
                description="关键词集合的 Jaccard 重合度",
                reference_value=0.65,
            ),
            TaskMetricDefinition(
                metric="LengthFit",
                description="输出篇幅与参考答案的贴合比值 (目标=1)",
                reference_value=1.0,
            ),
        ]

    # ------------------------------
    # 公共接口
    # ------------------------------
    def list_tasks(self) -> List[UrbanGovEvalTask]:
        return self._load_tasks()

    def run_evaluation(
        self,
        model_name: str,
        normalization_method: str = "ratio",
        task_limit: Optional[int] = None,
    ) -> UrbanGovEvalSummary:
        # 主流程：遍历每个任务，生成单任务评测结果，并最终汇总成整体报告
        tasks = self._load_tasks()
        limit = task_limit or self.default_task_limit
        if limit <= 0:
            limit = self.default_task_limit
        selected_tasks = tasks[: min(limit, len(tasks))]
        per_task_results: List[UrbanGovEvalPerTaskResult] = []
        now = datetime.utcnow()

        for task in selected_tasks:
            payload = self._task_payloads.get(task.task_id)
            if not payload:
                continue

            candidate_answer = self.answer_model.generate(payload.prompt_messages)
            judge_outputs = self.judge_model.score(
                task=task,
                candidate=candidate_answer,
                reference=payload.reference_answer,
                query=task.query,
            )
            # 依次评估标准项得分、归一化表现、事实性指标与任务专项指标
            criteria = self._evaluate_criteria(task, judge_outputs)
            race = self._compute_race(criteria, normalization_method)
            fact = self._evaluate_facts(
                task_id=task.task_id,
                task_domain=task.domain,
                candidate_answer=candidate_answer,
                reference_answer=payload.reference_answer,
                expectation=task.fact_expectation,
            )
            task_metrics = self._evaluate_task_metrics(
                candidate_answer=candidate_answer,
                reference_answer=payload.reference_answer,
                metric_defs=task.task_metrics,
            )

            per_task = UrbanGovEvalPerTaskResult(
                model_name=model_name,
                task_id=task.task_id,
                generated_at=now,
                normalization_method=normalization_method,
                race=race,
                criteria=criteria,
                fact=fact,
                task_metrics=task_metrics,
                metadata={
                    "title": task.title,
                    "domain": task.domain,
                    "task_type": task.task_type,
                    "difficulty": task.difficulty,
                    "time_ref": task.time_ref,
                    "reference_report": task.reference_report,
                    "candidate_answer": candidate_answer,
                    "reference_answer_excerpt": payload.reference_answer[:400],
                    "prompt_messages": payload.prompt_messages,
                },
            )
            self._save_per_task(per_task)
            per_task_results.append(per_task)

        summary = self._aggregate_summary(
            model_name=model_name,
            normalization_method=normalization_method,
            per_task_results=per_task_results,
            tasks=selected_tasks,
            task_limit=len(selected_tasks),
        )

        self._save_raw_data(model_name, per_task_results)
        self._save_summary(summary)
        self._update_leaderboard(summary)
        return summary

    def load_summary(self, model_name: str) -> Optional[UrbanGovEvalSummary]:
        # 读取历史汇总文件，方便快速查看既有评测结果
        summary_path = self.summary_dir / f"{model_name}_summary.json"
        if not summary_path.exists():
            return None
        with summary_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        data["generated_at"] = datetime.fromisoformat(data["generated_at"])
        data["race_ci"] = ConfidenceInterval(**data["race_ci"])
        data["citation_accuracy_ci"] = ConfidenceInterval(**data["citation_accuracy_ci"])
        data["overall_ci"] = ConfidenceInterval(**data["overall_ci"])
        data["domain_breakdown"] = [DomainScore(**item) for item in data["domain_breakdown"]]
        return UrbanGovEvalSummary(**data)

    def list_leaderboard(self) -> List[Dict[str, Any]]:
        leaderboard_path = self.summary_dir / "leaderboard.csv"
        if not leaderboard_path.exists():
            return []
        rows: List[Dict[str, Any]] = []
        with leaderboard_path.open("r", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                rows.append(
                    {
                        "model_name": row["model_name"],
                        "overall_score": float(row["overall_score"]),
                        "race_score": float(row["race_score"]),
                        "citation_accuracy": float(row["citation_accuracy"]),
                        "effective_citations_norm": float(row["effective_citations_norm"]),
                        "task_metrics_norm": float(row["task_metrics_norm"]),
                        "updated_at": row["updated_at"],
                    }
                )
        rows.sort(key=lambda item: item["overall_score"], reverse=True)
        return rows

    def load_per_task(self, model_name: str, task_id: str) -> Optional[UrbanGovEvalPerTaskResult]:
        per_task_path = self.per_task_dir / f"{model_name}_{task_id}.json"
        if not per_task_path.exists():
            return None
        with per_task_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        data["generated_at"] = datetime.fromisoformat(data["generated_at"])
        race_data = dict(data["race"])
        race_data["dimension_scores"] = [
            RaceDimensionScore(**item) for item in race_data.get("dimension_scores", [])
        ]
        race = RaceResult(**race_data)
        criteria = [CriterionScore(**item) for item in data["criteria"]]
        fact_raw = dict(data["fact"])
        pairs = [FactPairResult(**pair) for pair in fact_raw.get("pairs", [])]
        fact_raw.pop("pairs", None)
        fact = FactMetrics(**fact_raw, pairs=pairs)
        task_metrics = [TaskMetricScore(**item) for item in data["task_metrics"]]
        result = UrbanGovEvalPerTaskResult(
            model_name=model_name,
            task_id=task_id,
            generated_at=data["generated_at"],
            normalization_method=data["normalization_method"],
            race=race,
            criteria=criteria,
            fact=fact,
            task_metrics=task_metrics,
            metadata=data.get("metadata", {}),
        )
        self._ensure_fact_pairs_have_docs(result, save_if_changed=True)
        return result

    # ------------------------------
    # 评估子流程
    # ------------------------------
    def _evaluate_criteria(
        self,
        task: UrbanGovEvalTask,
        judge_outputs: Dict[str, Dict[str, Any]],
    ) -> List[CriterionScore]:
        results: List[CriterionScore] = []
        for criterion in task.criteria:
            judge_data = judge_outputs.get(criterion.id, {})
            target_score = float(
                round(_clamp(float(judge_data.get("score", criterion.reference_score)), 0.0, 10.0), 2)
            )
            gap = float(round(target_score - criterion.reference_score, 2))
            explanation = judge_data.get("explanation")
            if not explanation:
                if gap >= 0:
                    explanation = (
                        f"得分 {target_score:.1f} 高于参考值，基本满足“{criterion.description}”。"
                    )
                else:
                    explanation = (
                        f"得分 {target_score:.1f} 低于参考值，建议补充“{criterion.description}”相关内容。"
                    )

            results.append(
                CriterionScore(
                    criterion_id=criterion.id,
                    name=criterion.name,
                    dimension=criterion.dimension,
                    weight=criterion.weight,
                    target_score=target_score,
                    reference_score=criterion.reference_score,
                    gap=gap,
                    explanation=explanation,
                    reference_comment=criterion.reference_comment,
                )
            )
        return results

    def _compute_race(
        self,
        criteria: List[CriterionScore],
        normalization_method: str,
    ) -> RaceResult:
        # 汇总所有标准项得分，分别按比例法或相对优势法计算总体表现
        target_total = sum(item.weight * item.target_score for item in criteria)
        reference_total = sum(item.weight * item.reference_score for item in criteria)

        if reference_total == 0:
            reference_total = 1e-6
        if target_total == 0:
            target_total = 1e-6

        ratio_score = 100.0 * target_total / max(target_total, reference_total)
        relative_advantage = (
            50.0
            + 50.0
            * (target_total - reference_total)
            / (abs(target_total) + abs(reference_total) + 1e-6)
        )

        if normalization_method == "relative":
            normalized = relative_advantage
        else:
            normalized = ratio_score

        dimension_scores: Dict[str, Tuple[float, float]] = {}
        for item in criteria:
            dim = item.dimension
            weighted = item.weight * item.target_score
            if dim not in dimension_scores:
                dimension_scores[dim] = (0.0, 0.0)
            current_weighted, current_total_weight = dimension_scores[dim]
            dimension_scores[dim] = (
                current_weighted + weighted,
                current_total_weight + item.weight,
            )

        dimension_models: List[RaceDimensionScore] = []
        for dim, (weighted, weight_total) in dimension_scores.items():
            normalized_dim = (weighted / weight_total) * 10 if weight_total else 0.0
            dimension_models.append(
                RaceDimensionScore(
                    dimension=dim,
                    weighted_score=round(weighted, 3),
                    normalized_score=float(round(normalized_dim, 2)),
                )
            )

        return RaceResult(
            method=normalization_method,
            # normalized_score 根据 normalization_method 选用比例得分或相对优势分
            target_total=float(round(target_total, 3)),
            reference_total=float(round(reference_total, 3)),
            normalized_score=float(round(normalized, 2)),
            ratio_score=float(round(ratio_score, 2)),
            relative_advantage_score=float(round(relative_advantage, 2)),
            dimension_scores=dimension_models,
        )

    def _evaluate_facts(
        self,
        *,
        task_id: str,
        task_domain: Optional[str],
        candidate_answer: str,
        reference_answer: str,
        expectation: Optional[FactExpectation],
    ) -> FactMetrics:
        expectation_pairs = expectation.expected_pairs if expectation else 5
        pair_count = max(3, expectation_pairs)
        statements = _sentence_split(reference_answer)[:pair_count]
        if not statements:
            statements = _sentence_split(candidate_answer)[:pair_count] or ["需补充参考依据"]

        candidate_tokens = _tokenize(candidate_answer)
        pairs: List[FactPairResult] = []
        supported = 0
        authority = 0
        timely = 0
        misuse = 0

        for idx, statement in enumerate(statements, start=1):
            statement_tokens = _tokenize(statement)
            overlap = _overlap_ratio(statement_tokens, candidate_tokens)
            support_flag = overlap >= 0.35
            authority_flag = False
            timeliness_flag = False
            misuse_flag = not support_flag

            if support_flag:
                supported += 1
            if misuse_flag:
                misuse += 1

            knowledge_doc = self._pick_knowledge_doc(idx - 1, domain=task_domain)
            doc_note = None
            doc_meta = None
            if knowledge_doc:
                citation = self._build_doc_download_url(knowledge_doc)
                normalized_citation = knowledge_doc
                doc_meta = self._get_document_meta(knowledge_doc)
                doc_note = f"知识库引用《{knowledge_doc}》"
                if support_flag:
                    authority_flag = self._infer_authority_from_doc(knowledge_doc, doc_meta)
                    timeliness_flag = self._infer_timeliness_from_doc(knowledge_doc, doc_meta)
            else:
                citation = f"{self.question_bank_file.name}#{task_id}-{idx}"
                normalized_citation = f"general://{task_id}/{idx}"
                if support_flag:
                    authority_flag = (
                        _contains_keywords(candidate_answer, ["政府", "条例", "《", "部门", "局", "通告"]) > 0
                    )
                    timeliness_flag = _has_time_marker(candidate_answer)
            notes = f"关键词重合度 {overlap * 100:.1f}%"
            if doc_note:
                notes = f"{notes}；{doc_note}"
            pairs.append(
                FactPairResult(
                    statement=statement,
                    citation=citation,
                    normalized_citation=normalized_citation,
                    support=support_flag,
                    authority=authority_flag,
                    timeliness=timeliness_flag,
                    misuse=misuse_flag,
                    notes=notes,
                )
            )

            if authority_flag:
                authority += 1
            if timeliness_flag:
                timely += 1

        total_pairs = len(pairs)
        citation_accuracy = (supported / total_pairs) * 100 if total_pairs else 0.0
        source_authority_ratio = (authority / supported) * 100 if supported else 0.0
        timeliness_ratio = (timely / supported) * 100 if supported else 0.0
        misuse_rate = (misuse / total_pairs) * 100 if total_pairs else 0.0

        return FactMetrics(
            total_pairs=total_pairs,
            supported_pairs=supported,
            authoritative_pairs=authority,
            timely_pairs=timely,
            misuse_pairs=misuse,
            citation_accuracy=float(round(citation_accuracy, 2)),
            effective_citations=supported,
            source_authority_ratio=float(round(source_authority_ratio, 2)),
            timeliness_ratio=float(round(timeliness_ratio, 2)),
            misuse_rate=float(round(misuse_rate, 2)),
            pairs=pairs,
        )

    def _evaluate_task_metrics(
        self,
        *,
        candidate_answer: str,
        reference_answer: str,
        metric_defs: List[TaskMetricDefinition],
    ) -> List[TaskMetricScore]:
        scores: List[TaskMetricScore] = []
        candidate_tokens = _tokenize(candidate_answer)
        reference_tokens = _tokenize(reference_answer)
        for metric_def in metric_defs:
            direction = self._infer_metric_direction(metric_def)
            metric_key = metric_def.metric.lower()

            if metric_key == "rouge-l":
                value = _rouge_l(reference_tokens, candidate_tokens)
            elif metric_key == "tokenoverlap":
                value = _jaccard(reference_tokens, candidate_tokens)
            elif metric_key in {"lengthfit", "length_ratio"}:
                ref_len = max(len(reference_answer.strip()), 1)
                value = len(candidate_answer.strip()) / ref_len
            else:
                value = _overlap_ratio(reference_tokens, candidate_tokens)

            if metric_key in {"lengthfit", "length_ratio"}:
                normalized = max(0.0, 1.0 - abs(1.0 - value)) * 100
            elif direction == "higher_is_better":
                normalized = _clamp(value, 0.0, 1.0) * 100
            else:
                normalized = (1.0 - _clamp(value, 0.0, 1.0)) * 100

            scores.append(
                TaskMetricScore(
                    metric=metric_def.metric,
                    value=float(round(value, 3)),
                    normalized=float(round(normalized, 2)),
                    description=metric_def.description,
                    reference_value=metric_def.reference_value,
                    direction=direction,
                )
            )
        return scores

    def _infer_metric_direction(self, metric: TaskMetricDefinition) -> str:
        lower_keywords = ["violation", "误", "err", "rate", "违例", "error"]
        key = metric.metric.lower()
        if any(token in key for token in lower_keywords):
            return "lower_is_better"
        return "higher_is_better"

    # ------------------------------
    # 汇总
    # ------------------------------
    def _aggregate_summary(
        self,
        model_name: str,
        normalization_method: str,
        per_task_results: List[UrbanGovEvalPerTaskResult],
        tasks: List[UrbanGovEvalTask],
        task_limit: Optional[int] = None,
    ) -> UrbanGovEvalSummary:
        # 综合单任务结果，计算指标权重、领域排名及置信区间，形成模型评测总览
        race_scores = [item.race.normalized_score for item in per_task_results]
        citation_accuracy_values = [item.fact.citation_accuracy for item in per_task_results]
        misuse_values = [item.fact.misuse_rate for item in per_task_results]

        effective_norms: List[float] = []
        task_norms: List[float] = []

        task_lookup = {task.task_id: task for task in tasks}

        for result in per_task_results:
            task = task_lookup[result.task_id]
            expectation = task.fact_expectation
            if expectation and expectation.expected_pairs > 0:
                ec_norm = (
                    result.fact.effective_citations / expectation.expected_pairs * 100.0
                )
            else:
                ec_norm = result.fact.effective_citations * 10.0
            effective_norms.append(float(round(min(ec_norm, 100.0), 2)))

            if result.task_metrics:
                task_norms.append(
                    float(round(mean(score.normalized for score in result.task_metrics), 2))
                )

        race_avg = mean(race_scores) if race_scores else 0.0
        citation_accuracy_avg = mean(citation_accuracy_values) if citation_accuracy_values else 0.0
        effective_avg = mean(effective_norms) if effective_norms else 0.0
        task_metric_avg = mean(task_norms) if task_norms else 0.0

        overall = (
            0.40 * race_avg
            + 0.25 * citation_accuracy_avg
            + 0.15 * effective_avg
            + 0.20 * task_metric_avg
        )

        race_ci = self._bootstrap_ci(race_scores)
        citation_ci = self._bootstrap_ci(citation_accuracy_values)
        overall_ci = self._bootstrap_ci(
            [
                0.40 * race + 0.25 * ca + 0.15 * ec + 0.20 * tm
                for race, ca, ec, tm in zip(
                    race_scores or [race_avg],
                    citation_accuracy_values or [citation_accuracy_avg],
                    effective_norms or [effective_avg],
                    task_norms or [task_metric_avg],
                )
            ]
        )

        domain_breakdown = self._compute_domain_breakdown(
            per_task_results=per_task_results,
            tasks=tasks,
        )

        metrics_detail = {
            "race_scores": race_scores,
            "citation_accuracy_values": citation_accuracy_values,
            "effective_citations_norm": effective_norms,
            "task_metrics_norm": task_norms,
            "misuse_rates": misuse_values,
            "normalization_method": normalization_method,
        }

        total_available = len(self._tasks_cache) if self._tasks_cache else len(tasks)
        references: Dict[str, Any] = {
            "task_ids": [task.task_id for task in tasks],
            "task_count": len(tasks),
            "available_tasks": total_available,
            "question_bank": self.question_bank_file.name,
        }
        if task_limit is not None:
            references["task_limit"] = task_limit

        return UrbanGovEvalSummary(
            model_name=model_name,
            generated_at=datetime.utcnow(),
            normalization_method=normalization_method,
            task_count=len(tasks),
            race_score=float(round(race_avg, 2)),
            citation_accuracy=float(round(citation_accuracy_avg, 2)),
            effective_citations_norm=float(round(effective_avg, 2)),
            task_metrics_norm=float(round(task_metric_avg, 2)),
            overall_score=float(round(overall, 2)),
            race_ci=race_ci,
            citation_accuracy_ci=citation_ci,
            overall_ci=overall_ci,
            metrics=metrics_detail,
            domain_breakdown=domain_breakdown,
            references=references,
        )

    def _compute_domain_breakdown(
        self,
        per_task_results: List[UrbanGovEvalPerTaskResult],
        tasks: List[UrbanGovEvalTask],
    ) -> List[DomainScore]:
        # 以任务所属领域为单位聚合评分，帮助定位模型在不同治理领域的优势与短板
        mapping: Dict[str, List[Tuple[UrbanGovEvalPerTaskResult, UrbanGovEvalTask]]] = {}
        lookup = {task.task_id: task for task in tasks}

        for result in per_task_results:
            task = lookup[result.task_id]
            mapping.setdefault(task.domain, []).append((result, task))

        breakdown: List[DomainScore] = []
        for domain, items in mapping.items():
            race_vals = [item.race.normalized_score for item, _ in items]
            ca_vals = [item.fact.citation_accuracy for item, _ in items]
            effective_vals: List[float] = []
            task_metric_vals: List[float] = []

            for result, task in items:
                expectation = task.fact_expectation
                if expectation and expectation.expected_pairs > 0:
                    ec_norm = (
                        result.fact.effective_citations / expectation.expected_pairs * 100.0
                    )
                else:
                    ec_norm = result.fact.effective_citations * 10.0
                effective_vals.append(float(round(min(ec_norm, 100.0), 2)))

                if result.task_metrics:
                    task_metric_vals.append(
                        float(round(mean(score.normalized for score in result.task_metrics), 2))
                    )

            race_avg = mean(race_vals) if race_vals else 0.0
            ca_avg = mean(ca_vals) if ca_vals else 0.0
            effective_avg = mean(effective_vals) if effective_vals else 0.0
            task_metric_avg = mean(task_metric_vals) if task_metric_vals else 0.0
            overall = (
                0.40 * race_avg
                + 0.25 * ca_avg
                + 0.15 * effective_avg
                + 0.20 * task_metric_avg
            )

            breakdown.append(
                DomainScore(
                    domain=domain,
                    task_count=len(items),
                    race=float(round(race_avg, 2)),
                    citation_accuracy=float(round(ca_avg, 2)),
                    effective_citations_norm=float(round(effective_avg, 2)),
                    task_metrics_norm=float(round(task_metric_avg, 2)),
                    overall=float(round(overall, 2)),
                )
            )

        breakdown.sort(key=lambda item: item.overall, reverse=True)
        return breakdown

    def _bootstrap_ci(self, values: Iterable[float], iterations: int = 200) -> ConfidenceInterval:
        # 通过自助法估计指标的置信区间，衡量评测结果的稳定性
        values_list = [float(v) for v in values if v is not None]
        if not values_list:
            return ConfidenceInterval(lower=0.0, upper=0.0)
        if len(values_list) == 1:
            single = float(round(values_list[0], 2))
            return ConfidenceInterval(lower=single, upper=single)

        import random

        rng = random.Random(2025)
        means: List[float] = []
        length = len(values_list)
        for _ in range(iterations):
            sample = [values_list[rng.randrange(length)] for _ in range(length)]
            means.append(mean(sample))

        means.sort()
        lower_idx = int(0.025 * iterations)
        upper_idx = int(0.975 * iterations)
        lower = float(round(means[lower_idx], 2))
        upper = float(round(means[min(upper_idx, len(means) - 1)], 2))
        return ConfidenceInterval(lower=lower, upper=upper)

    # ------------------------------
    # 持久化
    # ------------------------------
    def _save_per_task(self, result: UrbanGovEvalPerTaskResult) -> None:
        path = self.per_task_dir / f"{result.model_name}_{result.task_id}.json"
        payload = result.model_dump()
        payload["generated_at"] = result.generated_at.isoformat()
        payload["race"]["dimension_scores"] = [
            item.model_dump() for item in result.race.dimension_scores
        ]
        payload["fact"] = result.fact.model_dump()
        payload["fact"]["pairs"] = [pair.model_dump() for pair in result.fact.pairs]
        payload["task_metrics"] = [item.model_dump() for item in result.task_metrics]
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

    def _save_raw_data(self, model_name: str, per_task_results: List[UrbanGovEvalPerTaskResult]) -> None:
        path = self.raw_dir / f"{model_name}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for result in per_task_results:
                record = {
                    "task_id": result.task_id,
                    "model_name": model_name,
                    "generated_at": result.generated_at.isoformat(),
                    "race_score": result.race.normalized_score,
                    "citation_accuracy": result.fact.citation_accuracy,
                    "effective_citations": result.fact.effective_citations,
                    "answer_preview": (result.metadata.get("candidate_answer") or "")[:160],
                    "reference_preview": (result.metadata.get("reference_answer_excerpt") or "")[:160],
                    "task_metrics": [
                        {
                            "metric": item.metric,
                            "value": item.value,
                            "normalized": item.normalized,
                        }
                        for item in result.task_metrics
                    ],
                }
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _save_summary(self, summary: UrbanGovEvalSummary) -> None:
        path = self.summary_dir / f"{summary.model_name}_summary.json"
        payload = summary.model_dump()
        payload["generated_at"] = summary.generated_at.isoformat()
        payload["race_ci"] = summary.race_ci.model_dump()
        payload["citation_accuracy_ci"] = summary.citation_accuracy_ci.model_dump()
        payload["overall_ci"] = summary.overall_ci.model_dump()
        payload["domain_breakdown"] = [item.model_dump() for item in summary.domain_breakdown]
        with path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)

    def _update_leaderboard(self, summary: UrbanGovEvalSummary) -> None:
        leaderboard_path = self.summary_dir / "leaderboard.csv"
        rows: Dict[str, Dict[str, Any]] = {}
        if leaderboard_path.exists():
            with leaderboard_path.open("r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    rows[row["model_name"]] = row

        rows[summary.model_name] = {
            "model_name": summary.model_name,
            "overall_score": f"{summary.overall_score:.2f}",
            "race_score": f"{summary.race_score:.2f}",
            "citation_accuracy": f"{summary.citation_accuracy:.2f}",
            "effective_citations_norm": f"{summary.effective_citations_norm:.2f}",
            "task_metrics_norm": f"{summary.task_metrics_norm:.2f}",
            "updated_at": summary.generated_at.isoformat(),
        }

        sorted_rows = sorted(
            rows.values(),
            key=lambda item: float(item["overall_score"]),
            reverse=True,
        )

        with leaderboard_path.open("w", encoding="utf-8", newline="") as fh:
            fieldnames = [
                "model_name",
                "overall_score",
                "race_score",
                "citation_accuracy",
                "effective_citations_norm",
                "task_metrics_norm",
                "updated_at",
            ]
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for row in sorted_rows:
                writer.writerow(row)


urban_gov_eval_service = UrbanGovEvalService()
