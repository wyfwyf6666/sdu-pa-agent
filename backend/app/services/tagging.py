from __future__ import annotations

import json
import logging
import os
from difflib import get_close_matches
from typing import Iterable, List, Sequence

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class TaggingService:
    """基于小模型的自动标签生成服务。"""

    def __init__(self) -> None:
        default_api_key = os.getenv("OPENAI_API_KEY", "")
        default_base_url = os.getenv("OPENAI_BASE_URL", "")
        self.client = AsyncOpenAI(api_key=default_api_key, base_url=default_base_url)
        self.model_name = os.getenv("TAGGING_MODEL_NAME", "gpt-4o")

    @staticmethod
    def _sanitize_tags(candidates: Iterable[str]) -> List[str]:
        seen = set()
        results: List[str] = []
        for item in candidates:
            if not item:
                continue
            tag = "".join(ch for ch in item.strip() if ch not in {"#", "·", "-", " "}).strip()
            if not tag:
                continue
            normalized = tag.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            results.append(tag)
        return results

    @staticmethod
    def _prefer_existing(candidates: Sequence[str], existing: Sequence[str]) -> List[str]:
        if not candidates:
            return []
        if not existing:
            return list(candidates)

        existing_map = {tag.lower(): tag for tag in existing if tag}
        final_tags: List[str] = []

        for candidate in candidates:
            key = candidate.lower()
            if key in existing_map:
                final_tags.append(existing_map[key])
                continue

            close = get_close_matches(candidate, existing_map.keys(), n=1, cutoff=0.8)
            if close:
                final_tags.append(existing_map[close[0]])
            else:
                final_tags.append(candidate)

        seen = set()
        ordered_unique: List[str] = []
        for tag in final_tags:
            lowered = tag.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            ordered_unique.append(tag)
        return ordered_unique

    @staticmethod
    def _parse_response(raw: str) -> List[str]:
        if not raw:
            return []

        raw = raw.strip()

        if raw.startswith("```"):
            lines = raw.splitlines()
            if lines:
                # drop opening fence
                lines = lines[1:]
                # drop closing fence if present
                while lines and lines[-1].strip().startswith("```"):
                    lines = lines[:-1]
                raw = "\n".join(lines).strip()

        if raw.startswith("["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                pass

        # 兼容 "1. 标签" 或换行分隔的返回
        lines = [line.strip() for line in raw.replace("，", ",").splitlines() if line.strip()]
        cleaned: List[str] = []
        for line in lines:
            if "." in line[:3]:
                _, _, remainder = line.partition(".")
                cleaned.append(remainder.strip())
            else:
                parts = [part.strip() for part in line.split(",") if part.strip()]
                cleaned.extend(parts or [line])
        return cleaned

    async def extract_metadata(
        self,
        text: str,
        category: str,
        existing_tags: Sequence[str],
    ) -> dict:
        """
        一次性提取文档的所有元数据，包括：
        - 标签（多个）
        - 分类特定字段（政策/论文/案例）
        """
        snippet = (text or "").strip()
        if not snippet:
            return {"tags": [], "category_fields": {}}
        snippet = snippet[:1500]

        existing_text = ", ".join(existing_tags) if existing_tags else "无"

        # 根据分类定义不同的提取字段
        category_fields_prompt = ""
        if category == "政策":
            category_fields_prompt = """
分类特定字段（每个字段只能有一个值）：
1. "effectiveness_level": 效力层级，只能是"中央"或"地方"之一
2. "document_type": 文件类型，如"条例"、"指导意见"、"通知"、"办法"、"规定"等
"""
        elif category == "论文":
            category_fields_prompt = """
分类特定字段（每个字段只能有一个值）：
1. "discipline": 学科维度，如"法学"、"工学"、"管理学"、"经济学"、"社会学"等
2. "main_topic": 主体内容，如"社区治理"、"智慧城市"、"城市规划"等
"""
        elif category == "案例":
            category_fields_prompt = """
分类特定字段（每个字段只能有一个值）：
1. "region": 地区，如"北京市"、"上海市"、"深圳市"等具体城市或地区
2. "main_topic": 主体内容，如"社区建设"、"服务优化"、"智慧治理"等
"""

        user_prompt = (
            "请阅读以下文档内容，提取文档元数据。\n\n"
            "要求：\n"
            "1. 标签（tags）：生成2-5个主题标签，标签应简短、具体，可以直接用于检索\n"
            "2. 如果候选标签与已有标签列表中的词语含义相同，请直接使用已有标签\n"
            "3. **重要**：标签不能与'主体内容'字段的值相同，标签应该是更细粒度的关键词\n"
            f"{category_fields_prompt}\n"
            "4. 返回格式必须是JSON对象，格式如下：\n"
            "{\n"
            '  "tags": ["标签1", "标签2", "标签3"],\n'
            '  "category_fields": {\n'
            '    "field_name": "字段值"\n'
            "  }\n"
            "}\n\n"
            f"已有标签列表：{existing_text}\n"
            f"文档类别：{category}\n"
            f"文档内容：\n{snippet}"
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个高效的中文元数据提取助手，擅长为城市治理知识库提取精准的标签和分类信息。",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=256,
            )
            raw_output = response.choices[0].message.content or ""

            # 尝试解析JSON
            raw_output = raw_output.strip()
            if raw_output.startswith("```"):
                lines = raw_output.splitlines()
                if lines:
                    lines = lines[1:]
                    while lines and lines[-1].strip().startswith("```"):
                        lines = lines[:-1]
                    raw_output = "\n".join(lines).strip()

            result = json.loads(raw_output)

            # 提取并清理标签
            raw_tags = result.get("tags", [])
            if isinstance(raw_tags, str):
                raw_tags = [raw_tags]
            sanitized_tags = self._sanitize_tags(raw_tags)

            # 保证标签数量
            if len(sanitized_tags) < 2:
                fallback_candidates = list(existing_tags)[:5]
                sanitized_tags.extend(self._sanitize_tags(fallback_candidates))

            preferred_tags = self._prefer_existing(sanitized_tags, existing_tags)

            # 提取分类特定字段
            category_fields = result.get("category_fields", {})
            if not isinstance(category_fields, dict):
                category_fields = {}

            # 过滤掉与main_topic相同的标签（在截断之前）
            main_topic = category_fields.get("main_topic", "").strip()
            if main_topic:
                # 过滤掉与主体内容相同的标签（不区分大小写）
                main_topic_lower = main_topic.lower()
                preferred_tags = [tag for tag in preferred_tags if tag.lower() != main_topic_lower]

            # 截断到最多5个
            limited_tags = preferred_tags[:5]

            # 如果过滤后标签太少，补充到最少2个
            if len(limited_tags) < 2 and category:
                limited_tags.append(category)

            return {
                "tags": limited_tags[:5],
                "category_fields": category_fields
            }

        except Exception as exc:
            logger.error("元数据提取失败: %s", exc)
            # 返回默认值
            return {
                "tags": [],
                "category_fields": {}
            }

    async def suggest_tags(
        self,
        text: str,
        existing_tags: Sequence[str],
        category: str | None = None,
        min_count: int = 2,
        max_count: int = 5,
    ) -> List[str]:
        snippet = (text or "").strip()
        if not snippet:
            return []
        snippet = snippet[:1500]

        existing_text = ", ".join(existing_tags) if existing_tags else "无"
        category_hint = category or "未指定"
        user_prompt = (
            "请阅读以下文档内容，为其生成主题标签。\n"
            "要求：\n"
            f"1. 标签数量保持在 {min_count}-{max_count} 个；\n"
            "2. 标签应简短、具体，可以直接用于检索；\n"
            "3. 如果候选标签与已有标签列表中的词语含义相同，请直接使用已有标签；\n"
            "4. 仅返回 JSON 数组，如 [\"标签1\", \"标签2\" ...]，不需要额外说明。\n\n"
            f"已有标签列表：{existing_text}\n"
            f"文档类别：{category_hint}\n"
            f"文档内容：\n{snippet}"
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {
                        "role": "system",
                        "content": "你是一个高效的中文标签推荐助手，擅长为城市治理知识库提取精准标签。",
                    },
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=128,
            )
            raw_output = response.choices[0].message.content or ""
            parsed = self._parse_response(raw_output)
        except Exception as exc:  # pragma: no cover - 外部服务错误
            logger.error("标签生成模型调用失败: %s", exc)
            parsed = []

        sanitized = self._sanitize_tags(parsed)

        if len(sanitized) < min_count:
            # 将已有标签作为补充，确保满足最小数量要求
            fallback_candidates = list(existing_tags)[: max_count]
            sanitized.extend(self._sanitize_tags(fallback_candidates))

        preferred = self._prefer_existing(sanitized, existing_tags)
        limited = preferred[:max_count]

        if len(limited) < min_count and category:
            limited.append(category)

        return limited[:max_count]


tagging_service = TaggingService()
