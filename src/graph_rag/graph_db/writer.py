"""
Neo4j 批量写入器 — 使用 UNWIND + MERGE 批量 upsert 节点和关系。

Cypher 模板从 schema.py 的 dataclass 字段和 REL_TYPES 方向自动生成，
无需手写维护。写入流程：write_nodes() → write_relations()（顺序不可反）。

依赖：
    - graph_db/connection.py（Neo4jDrivers）
    - graph_db/schema.py（节点/关系定义）
    - entity_extractor.py（Entity, Relation 模型）
"""

import os
import dataclasses
from typing import Optional

from graph_rag.config import get_settings
from graph_rag.entity_extractor import Entity, Relation
from graph_rag.graph_db.connection import Neo4jDrivers
from graph_rag.graph_db.schema import (
    NODE_TYPES, REL_TYPES,
    ModuleNode, FunctionNode, StepNode, RequirementNode,
    RegulationNode, ClauseNode, StandardNode,
    ZoneTypeNode, EquipmentTypeNode, EquipmentNode, ZoneNode,
)
from util_tools.logger import get_logger

logger = get_logger(__name__)


def _get_neo4j_driver() -> Neo4jDrivers:
    """懒加载 Neo4j 驱动。"""
    s = get_settings()
    return Neo4jDrivers(s.neo4j_uri, s.neo4j_user, s.neo4j_password, s.neo4j_database)


_N4JD: Neo4jDrivers | None = None


def _shared_neo4j() -> Neo4jDrivers:
    """进程级 Neo4j 驱动单例。"""
    global _N4JD
    if _N4JD is None:
        _N4JD = _get_neo4j_driver()
    return _N4JD


# ===================== Cypher 模板自动生成 =====================

# 每个节点类型的 MERGE 主键（唯一标识）。不在列表中的字段 → ON CREATE/ON MATCH。
# ponytail: 不用 dataclass required/default 推断，因为 Step.step_order 等
# 虽然必填但不是 Neo4j 唯一键，显式声明更安全。
_NODE_MERGE_KEYS = {
    "Module": ["name"], "Function": ["name"], "Step": ["name"],
    "Requirement": ["name"], "Regulation": ["name"], "Clause": ["name"],
    "Standard": ["name"], "ZoneType": ["name"], "EquipmentType": ["name"],
    "Equipment": ["equipment_id"], "Zone": ["zone_id"],
}

_NODE_DATACLASSES = {
    "Module": ModuleNode, "Function": FunctionNode, "Step": StepNode,
    "Requirement": RequirementNode, "Regulation": RegulationNode,
    "Clause": ClauseNode, "Standard": StandardNode,
    "ZoneType": ZoneTypeNode, "EquipmentType": EquipmentTypeNode,
    "Equipment": EquipmentNode, "Zone": ZoneNode,
}


def _build_merge_node_cypher() -> dict[str, str]:
    """从 dataclass 字段 + _NODE_MERGE_KEYS 自动生成节点 MERGE Cypher。"""
    templates = {}
    for label, cls in _NODE_DATACLASSES.items():
        merge_keys = set(_NODE_MERGE_KEYS.get(label, ["name"]))
        props = [f.name for f in dataclasses.fields(cls) if f.name not in merge_keys]

        key_assign = ", ".join(f"{k}: row.{k}" for k in _NODE_MERGE_KEYS.get(label, ["name"]))
        create_set = ", ".join(f"n.{p} = row.{p}" for p in props)
        match_set = ", ".join(f"n.{p} = COALESCE(row.{p}, n.{p})" for p in props)

        cypher = f"UNWIND $rows AS row\nMERGE (n:{label} {{{key_assign}}})"
        if create_set:
            cypher += f"\nON CREATE SET {create_set}"
        if match_set:
            cypher += f"\nON MATCH  SET {match_set}"
        templates[label] = cypher
    return templates


def _build_merge_rel_cypher() -> dict[str, str]:
    """从 REL_TYPES 方向定义自动生成关系 MERGE Cypher。

    REL_TYPES 格式: "包含功能": "Module → Function" → 解析出 source/target 标签。
    """
    templates = {}
    for rel_name, direction in REL_TYPES.items():
        # 解析 "SourceLabel → TargetLabel（注释）"
        dir_part = direction.split("（")[0].split("(")[0].strip()
        parts = dir_part.replace("→", "|").replace("->", "|").split("|")
        if len(parts) != 2:
            logger.warning(f"无法解析关系方向: {rel_name}: {direction}")
            continue
        src_label, tgt_label = parts[0].strip(), parts[1].strip()

        # 关系额外属性：仅"下一步"有 step_order
        rel_props = ""
        if rel_name == "下一步":
            rel_props = "r.step_order = row.step_order, "

        templates[rel_name] = (
            f"UNWIND $rows AS row\n"
            f"MATCH (s:{src_label} {{name: row.source_name}})\n"
            f"MATCH (t:{tgt_label} {{name: row.target_name}})\n"
            f"MERGE (s)-[r:{rel_name}]->(t)\n"
            f"ON CREATE SET {rel_props}r.description = row.description"
        )
    return templates


MERGE_NODE_CYPHER = _build_merge_node_cypher()
MERGE_REL_CYPHER = _build_merge_rel_cypher()


# ===================== Neo4j 批量写入器 =====================

class Neo4jBatchWriter:
    """Neo4j 批量写入器 — UNWIND + MERGE 批量 upsert。"""

    def __init__(self, driver: Neo4jDrivers | None = None, batch_size: int = 100):
        self.driver = driver or _shared_neo4j()
        self.batch_size = batch_size

    async def write_nodes(
        self, entities: list[Entity], extra_props: Optional[dict[str, dict]] = None,
    ) -> int:
        """批量写入节点。extra_props: 实体名 → 额外属性。"""
        return await self._batch_write(
            items=entities,
            templates=MERGE_NODE_CYPHER,
            key_fn=lambda e: e.type,
            row_fn=lambda e, ep: {"name": e.name, **ep.get(e.name, {})},
            label="节点",
            extra_props=extra_props,
        )

    async def write_relations(
        self, relations: list[Relation], extra_props: Optional[dict[str, dict]] = None,
    ) -> int:
        """批量写入关系。必须在 write_nodes() 之后调用。"""
        return await self._batch_write(
            items=relations,
            templates=MERGE_REL_CYPHER,
            key_fn=lambda r: r.relation,
            row_fn=lambda r, ep: {
                "source_name": r.source, "target_name": r.target,
                **ep.get(f"{r.source}→{r.target}", {}),
            },
            label="关系",
            extra_props=extra_props,
        )

    async def _batch_write(
        self, items, templates: dict, key_fn, row_fn, label: str,
        extra_props: Optional[dict[str, dict]] = None,
    ) -> int:
        """通用分组 → 查模板 → 映射 row → 分批执行。"""
        if not items:
            return 0

        groups: dict[str, list] = {}
        for item in items:
            groups.setdefault(key_fn(item), []).append(item)

        total = 0
        a_driver = await self.driver._get_async_driver()

        for type_key, group in groups.items():
            cypher = templates.get(type_key)
            if not cypher:
                logger.warning(f"无 MERGE 模板，跳过{label}类型: {type_key}")
                continue

            rows = [row_fn(item, extra_props or {}) for item in group]

            async with a_driver.session(database=self.driver.database) as session:
                for start in range(0, len(rows), self.batch_size):
                    batch = rows[start : start + self.batch_size]
                    try:
                        await session.run(cypher, {"rows": batch})
                        total += len(batch)
                    except Exception as e:
                        logger.error(f"Neo4j {label}写入失败: type={type_key}, batch={start}: {e}")
                        return total

            logger.debug(f"{label}写入: {type_key} × {len(rows)}")

        logger.info(f"{label}写入完成: 共 {total} 条")
        return total
