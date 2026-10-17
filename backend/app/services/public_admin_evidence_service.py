"""公共管理开放证据库

提供公共管理领域政府政策文件、统计年鉴、地方条例、学术文献等开放证据的
注册、检索和核验能力。只索引公开可访问的元数据和摘要，不抓取付费内容。
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

LOGGER = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = ROOT_DIR / "backend" / "data" / "public_admin_evidence"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

# ============================================================================
# Source Registry — 公共管理开放证据源注册表
# ============================================================================

PUBLIC_ADMIN_SOURCE_REGISTRY: List[Dict[str, Any]] = [
    # === 中央政府 ===
    {
        "id": "gov_cn_policy",
        "name": "中国政府网政策文件库",
        "category": "government_policy",
        "base_url": "https://www.gov.cn/zhengce/",
        "domain": "gov.cn",
        "source_level": "central",
        "authority_level": 95,
        "enabled": True,
    },
    {
        "id": "stats_gov_cn",
        "name": "国家统计局",
        "category": "statistics",
        "base_url": "https://www.stats.gov.cn/",
        "domain": "stats.gov.cn",
        "source_level": "central",
        "authority_level": 98,
        "enabled": True,
    },
    {
        "id": "mca_gov_cn",
        "name": "民政部",
        "category": "government_policy",
        "base_url": "https://www.mca.gov.cn/",
        "domain": "mca.gov.cn",
        "source_level": "central",
        "authority_level": 92,
        "enabled": True,
    },
    {
        "id": "mohrss_gov_cn",
        "name": "人力资源和社会保障部",
        "category": "government_policy",
        "base_url": "https://www.mohrss.gov.cn/",
        "domain": "mohrss.gov.cn",
        "source_level": "central",
        "authority_level": 92,
        "enabled": True,
    },
    {
        "id": "mohurd_gov_cn",
        "name": "住房和城乡建设部",
        "category": "government_policy",
        "base_url": "https://www.mohurd.gov.cn/",
        "domain": "mohurd.gov.cn",
        "source_level": "central",
        "authority_level": 92,
        "enabled": True,
    },
    {
        "id": "ndrc_gov_cn",
        "name": "国家发展改革委",
        "category": "government_policy",
        "base_url": "https://www.ndrc.gov.cn/",
        "domain": "ndrc.gov.cn",
        "source_level": "central",
        "authority_level": 92,
        "enabled": True,
    },
    {
        "id": "mof_gov_cn",
        "name": "财政部",
        "category": "government_policy",
        "base_url": "https://www.mof.gov.cn/",
        "domain": "mof.gov.cn",
        "source_level": "central",
        "authority_level": 92,
        "enabled": True,
    },
    {
        "id": "moe_gov_cn",
        "name": "教育部",
        "category": "government_policy",
        "base_url": "https://www.moe.gov.cn/",
        "domain": "moe.gov.cn",
        "source_level": "central",
        "authority_level": 92,
        "enabled": True,
    },
    {
        "id": "nhc_gov_cn",
        "name": "国家卫生健康委",
        "category": "government_policy",
        "base_url": "https://www.nhc.gov.cn/",
        "domain": "nhc.gov.cn",
        "source_level": "central",
        "authority_level": 92,
        "enabled": True,
    },
    {
        "id": "nhsa_gov_cn",
        "name": "国家医保局",
        "category": "government_policy",
        "base_url": "https://www.nhsa.gov.cn/",
        "domain": "nhsa.gov.cn",
        "source_level": "central",
        "authority_level": 92,
        "enabled": True,
    },
    {
        "id": "samr_gov_cn",
        "name": "市场监管总局",
        "category": "government_policy",
        "base_url": "https://www.samr.gov.cn/",
        "domain": "samr.gov.cn",
        "source_level": "central",
        "authority_level": 90,
        "enabled": True,
    },
    # === 地方人大/政府 ===
    {
        "id": "npc_gov_cn",
        "name": "中国人大网",
        "category": "regulation",
        "base_url": "https://www.npc.gov.cn/",
        "domain": "npc.gov.cn",
        "source_level": "central",
        "authority_level": 98,
        "enabled": True,
    },
    {
        "id": "chinalaw_gov_cn",
        "name": "中国政府法制信息网",
        "category": "regulation",
        "base_url": "https://www.chinalaw.gov.cn/",
        "domain": "chinalaw.gov.cn",
        "source_level": "central",
        "authority_level": 95,
        "enabled": True,
    },
    # === 地方（典型省级/市级门户） ===
    {
        "id": "zj_gov_cn",
        "name": "浙江省人民政府",
        "category": "government_policy",
        "base_url": "https://www.zj.gov.cn/",
        "domain": "zj.gov.cn",
        "source_level": "provincial",
        "authority_level": 88,
        "enabled": True,
    },
    {
        "id": "hangzhou_gov_cn",
        "name": "杭州市人民政府",
        "category": "government_policy",
        "base_url": "https://www.hangzhou.gov.cn/",
        "domain": "hangzhou.gov.cn",
        "source_level": "municipal",
        "authority_level": 85,
        "enabled": True,
    },
    {
        "id": "shanghai_gov_cn",
        "name": "上海市人民政府",
        "category": "government_policy",
        "base_url": "https://www.shanghai.gov.cn/",
        "domain": "shanghai.gov.cn",
        "source_level": "provincial",
        "authority_level": 90,
        "enabled": True,
    },
    {
        "id": "beijing_gov_cn",
        "name": "北京市人民政府",
        "category": "government_policy",
        "base_url": "https://www.beijing.gov.cn/",
        "domain": "beijing.gov.cn",
        "source_level": "provincial",
        "authority_level": 90,
        "enabled": True,
    },
    # === 开放学术源 ===
    {
        "id": "openalex",
        "name": "OpenAlex",
        "category": "academic",
        "base_url": "https://api.openalex.org/",
        "domain": "openalex.org",
        "source_level": "international",
        "authority_level": 80,
        "enabled": True,
    },
    {
        "id": "crossref",
        "name": "Crossref",
        "category": "academic",
        "base_url": "https://api.crossref.org/",
        "domain": "crossref.org",
        "source_level": "international",
        "authority_level": 88,
        "enabled": True,
    },
    {
        "id": "semantic_scholar",
        "name": "Semantic Scholar",
        "category": "academic",
        "base_url": "https://api.semanticscholar.org/",
        "domain": "semanticscholar.org",
        "source_level": "international",
        "authority_level": 82,
        "enabled": True,
    },
    {
        "id": "ncpssd",
        "name": "国家哲学社会科学文献中心",
        "category": "academic_cn",
        "base_url": "https://www.ncpssd.org/",
        "domain": "ncpssd.org",
        "source_level": "national",
        "authority_level": 85,
        "enabled": True,
        "note": "仅支持公开检索，不抓取受限内容",
    },
    # === 数据开放平台 ===
    {
        "id": "data_stats_gov_cn",
        "name": "国家统计局数据查询",
        "category": "statistics",
        "base_url": "https://data.stats.gov.cn/",
        "domain": "data.stats.gov.cn",
        "source_level": "central",
        "authority_level": 98,
        "enabled": True,
    },
    {
        "id": "data_zj_gov_cn",
        "name": "浙江数据开放平台",
        "category": "statistics",
        "base_url": "https://data.zj.gov.cn/",
        "domain": "data.zj.gov.cn",
        "source_level": "provincial",
        "authority_level": 85,
        "enabled": True,
    },
]


# ============================================================================
# Evidence Index (in-memory, backed by JSON)
# ============================================================================

class EvidenceIndex:
    """公共管理开放证据索引"""

    def __init__(self):
        self._documents: Dict[str, Dict[str, Any]] = {}
        self._index_path = EVIDENCE_DIR / "evidence_index.json"
        self._load()

    def _load(self):
        if self._index_path.exists():
            try:
                with open(self._index_path, "r", encoding="utf-8") as f:
                    self._documents = json.load(f)
                LOGGER.info("Loaded %d evidence documents", len(self._documents))
            except Exception as e:
                LOGGER.warning("Failed to load evidence index: %s", e)
                self._documents = {}

    def _save(self):
        try:
            with open(self._index_path, "w", encoding="utf-8") as f:
                json.dump(self._documents, f, ensure_ascii=False, indent=2)
        except Exception as e:
            LOGGER.error("Failed to save evidence index: %s", e)

    def add_document(self, doc: Dict[str, Any]) -> str:
        """添加证据文档"""
        doc_id = hashlib.md5(
            (doc.get("url", "") + doc.get("title", "")).encode()
        ).hexdigest()[:12]
        doc["id"] = doc_id
        doc["indexed_at"] = datetime.now().isoformat()
        self._documents[doc_id] = doc
        self._save()
        return doc_id

    def search(
        self,
        query: str = "",
        source_type: str = "",
        region: str = "",
        year: Optional[int] = None,
        top_k: int = 10,
    ) -> List[Dict[str, Any]]:
        """检索证据"""
        results: List[tuple[float, Dict[str, Any]]] = []

        for doc in self._documents.values():
            score = 0.0
            title = doc.get("title", "")
            abstract = doc.get("abstract", "")
            issuing = doc.get("issuing_authority", "")
            doc_region = doc.get("region", "")
            doc_year = doc.get("year")

            # Query matching
            if query:
                if query.lower() in title.lower():
                    score += 0.4
                elif query.lower() in abstract.lower():
                    score += 0.2
                elif any(w in title for w in query.split()):
                    score += 0.15

            # Type matching
            if source_type and doc.get("source_type") == source_type:
                score += 0.15

            # Region matching
            if region and doc_region and region in doc_region:
                score += 0.15

            # Year matching
            if year and doc_year and abs(int(doc_year) - year) <= 1:
                score += 0.1

            if score > 0.05:
                results.append((score, doc))

        results.sort(key=lambda x: x[0], reverse=True)
        return [
            {**doc, "match_score": round(s, 3)}
            for s, doc in results[:top_k]
        ]

    def search_regulation(self, title: str, region: str = "") -> List[Dict[str, Any]]:
        """专项检索条例/政策"""
        return self.search(
            query=title,
            source_type="regulation",
            region=region,
            top_k=5,
        )

    def get_source_registry(self, category: str = "") -> List[Dict[str, Any]]:
        """获取证据源注册表"""
        if category:
            return [s for s in PUBLIC_ADMIN_SOURCE_REGISTRY if s.get("category") == category]
        return PUBLIC_ADMIN_SOURCE_REGISTRY

    def get_stats(self) -> Dict[str, Any]:
        return {
            "total_documents": len(self._documents),
            "total_sources": len(PUBLIC_ADMIN_SOURCE_REGISTRY),
            "enabled_sources": len([s for s in PUBLIC_ADMIN_SOURCE_REGISTRY if s.get("enabled")]),
        }


# ============================================================================
# Public Admin Evidence Service
# ============================================================================

class PublicAdminEvidenceService:
    """公共管理开放证据库服务"""

    def __init__(self):
        self.index = EvidenceIndex()
        self.serper_api_key = os.getenv("SERPER_API_KEY", "")

    def verify_government_source(self, source_item: Dict[str, Any]) -> Dict[str, Any]:
        """验证政府数据来源"""
        result: Dict[str, Any] = {
            "verified": False,
            "confidence": 0.0,
            "matched_evidence": [],
            "missing_fields": [],
            "suggestion": "",
            "source_type": source_item.get("source_type", ""),
        }

        source_name = source_item.get("source_name", "")
        source_url = source_item.get("source_url")
        region = source_item.get("region", "")
        year = source_item.get("year")

        # 1. Check URL
        if source_url:
            is_gov = bool(re.search(r"\.gov\.cn", source_url))
            if is_gov:
                result["confidence"] = 0.7
                result["verified"] = True
                result["matched_evidence"].append({
                    "title": source_name,
                    "url": source_url,
                    "match_reason": "URL域名匹配gov.cn",
                    "match_score": 0.7,
                })
            else:
                result["confidence"] = 0.3

        # 2. Search evidence index
        if not result["matched_evidence"]:
            matches = self.index.search(
                query=source_name,
                source_type=source_item.get("source_type", ""),
                region=region,
                top_k=3,
            )
            if matches and matches[0]["match_score"] > 0.3:
                result["confidence"] = matches[0]["match_score"]
                result["matched_evidence"].append({
                    "title": matches[0].get("title", ""),
                    "url": matches[0].get("url", ""),
                    "match_score": matches[0]["match_score"],
                    "match_reason": "证据库匹配",
                })

        # 3. Web search fallback (if SERPER configured)
        if not result["matched_evidence"] and self.serper_api_key and source_name:
            web_results = self._web_search(source_name, region, year)
            if web_results:
                result["matched_evidence"].extend(web_results[:3])
                result["confidence"] = max(result["confidence"], 0.4)

        # 4. Missing field detection for government sources
        missing = []
        if source_item.get("source_type") in (
            "government_policy_document", "local_regulation"
        ):
            if not re.search(r"(?:文号|[\[\(（]\d{4}[\]\)）]\s*\d+)", source_item.get("source_text", "")):
                missing.append("document_number")
            if not re.search(r"(?:发布机关|颁布机关|发文机关)", source_item.get("source_text", "")):
                missing.append("issuing_authority")
            if not source_url:
                missing.append("official_url")

        result["missing_fields"] = missing
        result["suggestion"] = self._generate_source_suggestion(
            source_item, result["confidence"], missing
        )

        return result

    def _web_search(self, name: str, region: str = "", year: Any = None) -> List[Dict[str, Any]]:
        """联网搜索数据来源"""
        if not self.serper_api_key:
            return []
        query_parts = [name]
        if region:
            query_parts.append(region)
        if year:
            query_parts.append(str(year))
        query = " ".join(q for q in query_parts if q)[:200]

        try:
            import http.client
            conn = http.client.HTTPSConnection("google.serper.dev", timeout=10)
            payload = json.dumps({"q": query, "gl": "cn", "hl": "zh-cn"})
            headers = {"X-API-KEY": self.serper_api_key, "Content-Type": "application/json"}
            conn.request("POST", "/search", payload, headers)
            resp = conn.getresponse()
            if resp.status != 200:
                conn.close()
                return []
            data = json.loads(resp.read().decode("utf-8"))
            conn.close()

            results = []
            for item in data.get("organic", [])[:3]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "match_reason": "联网搜索",
                    "match_score": 0.35,
                })
            return results
        except Exception as e:
            LOGGER.warning("Evidence web search failed: %s", e)
            return []

    def _generate_source_suggestion(
        self, item: Dict[str, Any], confidence: float, missing: List[str]
    ) -> str:
        """生成来源验证建议"""
        source_type = item.get("source_type", "")
        name = item.get("source_name", "该来源")

        if source_type in ("government_policy_document", "local_regulation"):
            parts = [
                f"建议补充「{name}」的发布机关、通过日期、施行日期、文号、"
                "现行有效状态和官方发布链接。",
                "优先引用中国政府网、地方人大网、司法行政部门官网或地方政府官网的正式文本。",
            ]
        elif source_type in ("statistical_yearbook", "statistical_bureau_data"):
            parts = [
                f"建议补充「{name}」的年鉴全称、年份、表号、指标名称、"
                "统计口径、地区范围和页码。",
            ]
        else:
            parts = [f"建议补充「{name}」的发布机构、发布日期和可访问链接。"]

        if missing:
            parts.append(f"当前缺失：{'、'.join(missing)}。")

        if confidence < 0.5:
            parts.append("建议通过联网搜索或图书馆资源进一步确认该来源是否存在。")

        return " ".join(parts)

    def add_seed_evidence(self) -> int:
        """添加公共管理领域的种子证据文档（示例）"""
        seed_docs = [
            {
                "title": "杭州市居家养老服务条例",
                "source_type": "local_regulation",
                "issuing_authority": "杭州市人民代表大会常务委员会",
                "publish_date": "2021-06-01",
                "document_number": "杭人大常〔2021〕12号",
                "region": "杭州",
                "year": 2021,
                "url": "https://www.hangzhou.gov.cn/art/2021/6/1/art_1229063382_12345.html",
                "abstract": "为了积极应对人口老龄化，规范居家养老服务工作，保障老年人合法权益...",
                "topic_tags": ["养老服务", "居家养老", "社会保障"],
            },
            {
                "title": "中国城市统计年鉴2022",
                "source_type": "statistical_yearbook",
                "issuing_authority": "国家统计局城市社会经济调查司",
                "publish_date": "2022-12-01",
                "region": "全国",
                "year": 2022,
                "url": "https://www.stats.gov.cn/sj/ndsj/2022/indexch.htm",
                "abstract": "收录了全国城市经济社会统计资料...",
                "topic_tags": ["城市统计", "统计年鉴", "城市数据"],
            },
            {
                "title": "数字政府建设指导意见",
                "source_type": "government_policy_document",
                "issuing_authority": "国务院",
                "publish_date": "2022-06-23",
                "document_number": "国发〔2022〕14号",
                "region": "全国",
                "year": 2022,
                "url": "https://www.gov.cn/zhengce/content/2022-06/23/content_5697294.htm",
                "abstract": "加强数字政府建设是适应新一轮科技革命和产业变革趋势的必然要求...",
                "topic_tags": ["数字政府", "政府治理", "数字化转型"],
            },
            {
                "title": "关于推进养老服务发展的意见",
                "source_type": "government_policy_document",
                "issuing_authority": "国务院办公厅",
                "publish_date": "2019-04-16",
                "document_number": "国办发〔2019〕5号",
                "region": "全国",
                "year": 2019,
                "url": "https://www.gov.cn/zhengce/content/2019-04/16/content_5383270.htm",
                "abstract": "为深化养老服务供给侧结构性改革...",
                "topic_tags": ["养老服务", "社会保障", "民生"],
            },
            {
                "title": "浙江省数字经济促进条例",
                "source_type": "local_regulation",
                "issuing_authority": "浙江省人民代表大会常务委员会",
                "publish_date": "2020-12-24",
                "region": "浙江",
                "year": 2020,
                "url": "https://www.zj.gov.cn/art/2020/12/24/art_1229017136_59000000.html",
                "abstract": "为了促进数字经济发展，加快建设现代化经济体系...",
                "topic_tags": ["数字经济", "数字治理", "地方条例"],
            },
        ]

        count = 0
        for doc in seed_docs:
            self.index.add_document(doc)
            count += 1
        LOGGER.info("Added %d seed evidence documents", count)
        return count


# ============================================================================
# Evidence Routes helper (for router integration)
# ============================================================================

def build_evidence_index(
    source_categories: Optional[List[str]] = None,
    max_pages_per_source: int = 100,
    respect_robots: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """构建公共管理开放证据索引"""
    service = PublicAdminEvidenceService()

    if dry_run:
        return {
            "status": "dry_run",
            "sources_found": len(PUBLIC_ADMIN_SOURCE_REGISTRY),
            "enabled_sources": len(
                [s for s in PUBLIC_ADMIN_SOURCE_REGISTRY if s.get("enabled")]
            ),
            "message": "未执行实际抓取（dry_run模式）。",
        }

    # Add seed data
    count = service.add_seed_evidence()

    return {
        "status": "completed",
        "documents_added": count,
        "total_documents": service.index.get_stats()["total_documents"],
        "message": f"已添加 {count} 条种子证据文档到索引。",
    }


# 全局实例
evidence_service = PublicAdminEvidenceService()
