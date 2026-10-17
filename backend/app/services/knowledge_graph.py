from __future__ import annotations

import json
import logging
import threading
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class KnowledgeGraphService:
    """负责加载 youtu-graphrag/city.json 并提供查询/可视化数据。"""

    def __init__(self) -> None:
        root_dir = Path(__file__).resolve().parents[3]
        self._graph_file = root_dir / "backend" / "data" / "city.json"
        self._lock = threading.Lock()
        self._triples: List[Dict[str, str]] = []
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._neighbors: Dict[str, Set[str]] = defaultdict(set)
        self._predicate_counter: Counter[str] = Counter()
        self._last_loaded: Optional[datetime] = None
        self._data_available = False

        try:
            self._load_graph()
        except FileNotFoundError:
            logger.warning("Knowledge graph source file missing: %s", self._graph_file)

    # --------------------------------------------------------------------- #
    # 数据加载
    # --------------------------------------------------------------------- #
    def _load_graph(self) -> None:
        """加载并解析 city.json。"""
        if not self._graph_file.exists():
            raise FileNotFoundError(f"未找到知识图谱数据文件: {self._graph_file}")

        with self._lock:
            with open(self._graph_file, "r", encoding="utf-8") as file:
                raw_data = json.load(file)

            triples: List[Dict[str, str]] = []
            nodes: Dict[str, Dict[str, Any]] = {}
            neighbors: Dict[str, Set[str]] = defaultdict(set)
            predicate_counter: Counter[str] = Counter()

            for index, entry in enumerate(raw_data):
                subject = str(entry.get("subject", "")).strip()
                predicate = str(entry.get("predicate", "")).strip()
                obj = str(entry.get("object", "")).strip()

                if not subject or not predicate or not obj:
                    continue

                triple_id = entry.get("@id") or f"triple_{index + 1:04d}"
                triple = {
                    "id": triple_id,
                    "subject": subject,
                    "predicate": predicate,
                    "object": obj,
                }
                triples.append(triple)
                predicate_counter[predicate] += 1

                for value in (subject, obj):
                    if value not in nodes:
                        nodes[value] = {
                            "id": value,
                            "name": value,
                            "degree": 0,
                            "occurrences": 0,
                        }
                    nodes[value]["degree"] += 1
                    nodes[value]["occurrences"] += 1

                neighbors[subject].add(obj)
                neighbors[obj].add(subject)

            self._triples = triples
            self._nodes = nodes
            self._neighbors = neighbors
            self._predicate_counter = predicate_counter
            self._last_loaded = datetime.now(timezone.utc)
            self._data_available = True

            logger.info(
                "Knowledge graph loaded: %d triples, %d nodes, %d predicates",
                len(self._triples),
                len(self._nodes),
                len(self._predicate_counter),
            )

    def reload(self) -> Dict[str, Any]:
        """手动触发重新加载。"""
        self._load_graph()
        return {
            "reloaded": True,
            "triples": len(self._triples),
            "nodes": len(self._nodes),
            "predicates": len(self._predicate_counter),
            "last_loaded": self._last_loaded.isoformat() if self._last_loaded else None,
        }

    def _ensure_ready(self) -> None:
        if not self._data_available:
            self._load_graph()
        if not self._data_available:
            raise FileNotFoundError(f"知识图谱数据不可用，请确认 {self._graph_file} 是否存在")

    # --------------------------------------------------------------------- #
    # 对外数据接口
    # --------------------------------------------------------------------- #
    def get_overview(self) -> Dict[str, Any]:
        """获取节点、三元组、谓词等总体信息。"""
        self._ensure_ready()
        top_predicates = [
            {"predicate": name, "count": count}
            for name, count in self._predicate_counter.most_common(6)
        ]
        top_entities = sorted(
            (
                {"name": node["name"], "degree": node["degree"]}
                for node in self._nodes.values()
            ),
            key=lambda item: item["degree"],
            reverse=True,
        )[:6]

        return {
            "node_count": len(self._nodes),
            "triple_count": len(self._triples),
            "predicate_count": len(self._predicate_counter),
            "top_predicates": top_predicates,
            "top_entities": top_entities,
            "last_loaded": self._last_loaded.isoformat() if self._last_loaded else None,
            "source_file": str(self._graph_file),
        }

    def get_predicates(self) -> List[Dict[str, Any]]:
        """返回谓词列表及计数，用于筛选。"""
        self._ensure_ready()
        return [
            {"predicate": name, "count": count}
            for name, count in self._predicate_counter.most_common()
        ]

    def search_triples(
        self,
        query: Optional[str] = None,
        predicate: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> Dict[str, Any]:
        """支持关键词与谓词过滤的分页查询。"""
        self._ensure_ready()
        filtered = self._triples

        if predicate:
            filtered = [item for item in filtered if item["predicate"] == predicate]

        if query:
            keyword = query.lower()
            filtered = [
                item
                for item in filtered
                if keyword in item["subject"].lower()
                or keyword in item["predicate"].lower()
                or keyword in item["object"].lower()
            ]

        total = len(filtered)
        start = max(0, (page - 1) * page_size)
        end = start + page_size
        items = filtered[start:end]

        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "predicates": self.get_predicates(),
        }

    def _resolve_node_name(self, target: Optional[str]) -> Optional[str]:
        if not target:
            return None
        target = target.strip()
        if target in self._nodes:
            return target

        target_lower = target.lower()
        for name in self._nodes.keys():
            if target_lower in name.lower():
                return name
        return None

    def _categorize_node(self, degree: int, center: Optional[str], name: str) -> str:
        if center and name == center:
            return "核心实体"
        if degree >= 8:
            return "关键实体"
        if degree >= 4:
            return "重要实体"
        return "普通实体"

    def get_graph_view(
        self,
        center: Optional[str] = None,
        depth: int = 1,
        limit: int = 120,
    ) -> Dict[str, Any]:
        """根据中心节点和深度生成前端图谱数据。"""
        self._ensure_ready()
        depth = max(1, min(depth, 5))
        limit = max(20, min(limit, 300))

        resolved_center = self._resolve_node_name(center)
        selected_nodes: Set[str] = set()

        if resolved_center:
            queue: deque[Tuple[str, int]] = deque([(resolved_center, 0)])
            selected_nodes.add(resolved_center)

            while queue and len(selected_nodes) < limit:
                node, current_depth = queue.popleft()
                if current_depth >= depth:
                    continue
                for neighbor in self._neighbors.get(node, []):
                    if neighbor not in selected_nodes:
                        selected_nodes.add(neighbor)
                        queue.append((neighbor, current_depth + 1))
                    if len(selected_nodes) >= limit:
                        break
        else:
            # 默认选择度数最高的节点
            sorted_nodes = sorted(
                self._nodes.values(),
                key=lambda item: item["degree"],
                reverse=True,
            )
            for node in sorted_nodes[:limit]:
                selected_nodes.add(node["name"])

        nodes_payload: List[Dict[str, Any]] = []
        if selected_nodes:
            degrees = [
                self._nodes.get(name, {}).get("degree", 0) for name in selected_nodes
            ]
            max_degree = max(degrees) if degrees else 0
            min_degree = min(degrees) if degrees else 0
            size_min, size_max = 16, 46

            def scale_symbol_size(current_degree: int) -> float:
                if max_degree == min_degree:
                    return float(size_max if current_degree else size_min)
                ratio = (current_degree - min_degree) / (max_degree - min_degree)
                return float(size_min + ratio * (size_max - size_min))

            for name in selected_nodes:
                node_info = self._nodes.get(name)
                if not node_info:
                    continue
                degree = node_info["degree"]
                category = self._categorize_node(degree, resolved_center, name)
                nodes_payload.append(
                    {
                        "id": name,
                        "name": name,
                        "degree": degree,
                        "category": category,
                        "symbol_size": scale_symbol_size(degree),
                        "is_center": resolved_center == name,
                        "value": degree,
                    }
                )

        predicate_nodes: Dict[str, Set[str]] = defaultdict(set)
        for triple in self._triples:
            if triple["subject"] in selected_nodes:
                predicate_nodes[triple["predicate"]].add(triple["subject"])
            if triple["object"] in selected_nodes:
                predicate_nodes[triple["predicate"]].add(triple["object"])

        edges_payload: List[Dict[str, Any]] = []
        existing_pairs: Set[Tuple[str, str]] = set()
        for triple in self._triples:
            if triple["subject"] in selected_nodes and triple["object"] in selected_nodes:
                pair_key = tuple(sorted((triple["subject"], triple["object"])))
                if pair_key in existing_pairs:
                    continue
                edges_payload.append(
                    {
                        "id": triple["id"],
                        "source": triple["subject"],
                        "target": triple["object"],
                        "label": triple["predicate"],
                        "is_inferred": False,
                    }
                )
                existing_pairs.add(pair_key)
            if len(edges_payload) >= limit * 4:
                break

        max_inferred_edges = min(200, max(40, limit * 2))
        inferred_count = 0
        for predicate, nodes in predicate_nodes.items():
            relevant_nodes = [name for name in nodes if name in selected_nodes]
            if len(relevant_nodes) < 2:
                continue
            relevant_nodes.sort(
                key=lambda node: self._nodes.get(node, {}).get("degree", 0),
                reverse=True,
            )
            for idx in range(len(relevant_nodes) - 1):
                src = relevant_nodes[idx]
                tgt = relevant_nodes[idx + 1]
                pair_key = tuple(sorted((src, tgt)))
                if pair_key in existing_pairs:
                    continue
                edges_payload.append(
                    {
                        "id": f"infer_{predicate}_{inferred_count}",
                        "source": src,
                        "target": tgt,
                        "label": f"推理:{predicate}",
                        "is_inferred": True,
                    }
                )
                existing_pairs.add(pair_key)
                inferred_count += 1
                if inferred_count >= max_inferred_edges:
                    break
            if inferred_count >= max_inferred_edges:
                break

        categories = sorted({node["category"] for node in nodes_payload})

        return {
            "nodes": nodes_payload,
            "edges": edges_payload,
            "categories": categories,
            "center": resolved_center,
            "total_nodes": len(selected_nodes),
        }


knowledge_graph_service = KnowledgeGraphService()
