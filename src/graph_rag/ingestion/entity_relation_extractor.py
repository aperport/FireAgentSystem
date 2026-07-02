"""
实体/关系抽取模块 — 从知识文档中抽取实体和关系写入 Neo4j 知识图谱。

✅ 已实现。抽取目标：
    1. 法规关联子图：
        - 法规名 → Regulation 节点
        - 条款号/内容 → Clause 节点
        - 条款引用关系 → 引用 边
        - 适用场所类型 → 适用法规 边
        - 设备配置要求 → 要求配置 边

    2. 系统操作子图：
        - 模块名 → Module 节点
        - 功能名 → Function 节点
        - 操作步骤 → Step 节点
        - 前置条件 → Requirement 节点

抽取方式：
    - LLM 结构化输出提取（继承 EntityExtractor，复用 with_structured_output 保证输出格式）
    - NER 小模型补充（继承 EntityExtractor，复用 BERT NER 管道）
    - 规则辅助（条款号格式识别：第X条第X款、X.X节等正则匹配）

抽取结果写入 Neo4j（通过 graph_db/connection.py 的 Neo4jDrivers），
使用 UNWIND + MERGE 批量写入，保证幂等（重复执行不产生重复节点/关系）。

已实现：
    1. DocumentEntityExtractor — 文档模式实体抽取（继承 EntityExtractor，覆盖 prompt）
    2. 规则辅助抽取 — 条款号正则匹配（第X条第X款、X.X节、X.X.X条等）
    3. Neo4j 批量写入 — UNWIND + MERGE 批量 upsert 节点和关系
    4. 段落级抽取管线 — 按文档章节逐段抽取，控制单次 LLM 输入长度
    5. 抽取结果校验 — 与 schema.py 的节点/关系定义对齐

依赖：
    - entity_extractor.py（继承 EntityExtractor，复用 LLM/NER/融合逻辑）
    - graph_db/connection.py（Neo4j 连接）
    - graph_db/schema.py（节点/关系结构约束）
"""

import os
import re
import asyncio
from typing import Optional

from langchain_openai import ChatOpenAI

# 从查询侧导入已有的抽取引擎和模型定义
from graph_rag.entity_extractor import EntityExtractor, Entity, Relation, ExtractResult
from graph_rag.graph_db.connection import Neo4jDrivers
from util_tools.logger import get_logger

logger = get_logger(__name__)

# ─── Neo4j 连接（模块级，与 graph_traverser.py 模式一致）───
# 从环境变量读取连接参数，延迟初始化
_N4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
_N4J_USER = os.getenv("NEO4J_USER", "neo4j")
_N4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "neo4j")
N4JD = Neo4jDrivers(_N4J_URI, _N4J_USER, _N4J_PASSWORD)


# ===================== 条款号正则模式 =====================
# 按优先级排列：最具体的模式在前，避免被宽泛模式提前匹配
# 例如 "第一条第一款" 应被第1个模式匹配，而非被第4个 "第一条" 匹配
CLAUSE_PATTERNS: list[re.Pattern] = [
    # 第X条第X款（中文数字）
    re.compile(r"第[一二三四五六七八九十百千]+条第[一二三四五六七八九十]+款"),
    # 第X条第X款（阿拉伯数字）
    re.compile(r"第\d+条第\d+款"),
    # X.X.X节 / X.X.X条（阿拉伯数字+点号，如 5.1.1节、5.1.1条）
    re.compile(r"\d+\.\d+(?:\.\d+)?(?:节|条)"),
    # X.X节（两位版本，如 5.1节）
    re.compile(r"\d+\.\d+节"),
    # 第X条（中文数字）
    re.compile(r"第[一二三四五六七八九十百千]+条"),
    # 第X条（阿拉伯数字）
    re.compile(r"第\d+条"),
]


# ===================== Cypher 写入模板 =====================
# 使用 UNWIND + MERGE 批量写入，MERGE 保证幂等（重复执行不产生重复节点/关系）
# 参数 $rows 是一个列表，每项是字典，包含节点的属性值
#
# ON CREATE SET：首次创建时设置属性
# ON MATCH SET：已存在时更新属性（COALESCE 保留已有值，避免覆盖为 None）
#
# ⚠️ 关系的 MERGE 必须先 MATCH 到起终节点，否则关系创建失败
#    因此 write_relations() 必须在 write_nodes() 之后调用

MERGE_NODE_CYPHER: dict[str, str] = {
    # ── 法规关联子图 ──

    "Regulation": """
    UNWIND $rows AS row
    MERGE (n:Regulation {name: row.name})
    ON CREATE SET n.code = row.code, n.description = row.description
    ON MATCH  SET n.code = COALESCE(row.code, n.code),
               n.description = COALESCE(row.description, n.description)
    """,

    "Clause": """
    UNWIND $rows AS row
    MERGE (n:Clause {name: row.name})
    ON CREATE SET n.content = row.content, n.regulation_name = row.regulation_name
    ON MATCH  SET n.content = COALESCE(row.content, n.content),
               n.regulation_name = COALESCE(row.regulation_name, n.regulation_name)
    """,

    "Standard": """
    UNWIND $rows AS row
    MERGE (n:Standard {name: row.name})
    ON CREATE SET n.code = row.code, n.description = row.description
    ON MATCH  SET n.code = COALESCE(row.code, n.code),
               n.description = COALESCE(row.description, n.description)
    """,

    # ── 系统操作子图 ──

    "Module": """
    UNWIND $rows AS row
    MERGE (n:Module {name: row.name})
    ON CREATE SET n.description = row.description
    """,

    "Function": """
    UNWIND $rows AS row
    MERGE (n:Function {name: row.name})
    ON CREATE SET n.module_name = row.module_name, n.description = row.description
    ON MATCH  SET n.module_name = COALESCE(row.module_name, n.module_name),
               n.description = COALESCE(row.description, n.description)
    """,

    "Step": """
    UNWIND $rows AS row
    MERGE (n:Step {name: row.name})
    ON CREATE SET n.step_order = row.step_order, n.function_name = row.function_name,
                   n.description = row.description
    ON MATCH  SET n.step_order = COALESCE(row.step_order, n.step_order),
               n.function_name = COALESCE(row.function_name, n.function_name),
               n.description = COALESCE(row.description, n.description)
    """,

    "Requirement": """
    UNWIND $rows AS row
    MERGE (n:Requirement {name: row.name})
    ON CREATE SET n.step_name = row.step_name, n.description = row.description
    ON MATCH  SET n.step_name = COALESCE(row.step_name, n.step_name),
               n.description = COALESCE(row.description, n.description)
    """,

    # ── 分类与规格 ──

    "ZoneType": """
    UNWIND $rows AS row
    MERGE (n:ZoneType {name: row.name})
    ON CREATE SET n.risk_level = row.risk_level, n.description = row.description
    ON MATCH  SET n.risk_level = COALESCE(row.risk_level, n.risk_level),
               n.description = COALESCE(row.description, n.description)
    """,

    "EquipmentType": """
    UNWIND $rows AS row
    MERGE (n:EquipmentType {name: row.name})
    ON CREATE SET n.category = row.category, n.description = row.description
    ON MATCH  SET n.category = COALESCE(row.category, n.category),
               n.description = COALESCE(row.description, n.description)
    """,
}

MERGE_REL_CYPHER: dict[str, str] = {
    # ── 法规关联子图 ──

    "包含条款": """
    UNWIND $rows AS row
    MATCH (s:Regulation {name: row.source_name})
    MATCH (t:Clause {name: row.target_name})
    MERGE (s)-[r:包含条款]->(t)
    ON CREATE SET r.description = row.description
    """,

    "引用": """
    UNWIND $rows AS row
    MATCH (s:Clause {name: row.source_name})
    MATCH (t:Standard {name: row.target_name})
    MERGE (s)-[r:引用]->(t)
    ON CREATE SET r.description = row.description
    """,

    "适用法规": """
    UNWIND $rows AS row
    MATCH (s:ZoneType {name: row.source_name})
    MATCH (t:Regulation {name: row.target_name})
    MERGE (s)-[r:适用法规]->(t)
    ON CREATE SET r.description = row.description
    """,

    "要求配置": """
    UNWIND $rows AS row
    MATCH (s:Clause {name: row.source_name})
    MATCH (t:EquipmentType {name: row.target_name})
    MERGE (s)-[r:要求配置]->(t)
    ON CREATE SET r.description = row.description
    """,

    # ── 系统操作子图 ──

    "包含功能": """
    UNWIND $rows AS row
    MATCH (s:Module {name: row.source_name})
    MATCH (t:Function {name: row.target_name})
    MERGE (s)-[r:包含功能]->(t)
    ON CREATE SET r.description = row.description
    """,

    "操作步骤": """
    UNWIND $rows AS row
    MATCH (s:Function {name: row.source_name})
    MATCH (t:Step {name: row.target_name})
    MERGE (s)-[r:操作步骤]->(t)
    ON CREATE SET r.description = row.description
    """,

    "下一步": """
    UNWIND $rows AS row
    MATCH (s:Step {name: row.source_name})
    MATCH (t:Step {name: row.target_name})
    MERGE (s)-[r:下一步]->(t)
    ON CREATE SET r.step_order = row.step_order, r.description = row.description
    """,

    "前置条件": """
    UNWIND $rows AS row
    MATCH (s:Step {name: row.source_name})
    MATCH (t:Requirement {name: row.target_name})
    MERGE (s)-[r:前置条件]->(t)
    ON CREATE SET r.description = row.description
    """,
}


# ===================== 文档模式实体抽取器 =====================

class DocumentEntityExtractor(EntityExtractor):
    """文档模式实体抽取器 — 继承 EntityExtractor，覆盖 prompt 为文档抽取模式。

    与查询端 EntityExtractor 的区别：
        - query 模式：从用户问题中提取，约束"仅提取问题中明确提及的实体"
        - document 模式：从文档段落中提取，约束"提取段落中所有实体和关系"

    复用的方法（来自父类，无需重写）：
        - entity_extract_llm()    LLM 结构化抽取（with_structured_output）
        - entity_extract_ner()    NER 小模型抽取（BERT 管道）
        - merge_results()         LLM+NER 结果融合（LLM 为主，NER 补充）
        - _is_similar()           文本相似度判断（包含关系/字符重叠率）
        - main_pip()              异步管线入口（LLM+NER 并行 → 融合）

    Args:
        llm_client: LLM 客户端（ChatOpenAI 实例）
        text: 文档段落文本（传给父类的 query 参数，NER 也用此文本）
        context: 段落上下文（如标题链 "消防法 > 第三章 > 第十五条"），
                 用于 prompt 增强，帮助 LLM 理解段落位置
        config: RunnableConfig
        entity_extract_model: NER 模型名
    """

    def __init__(
        self,
        llm_client: ChatOpenAI,
        text: str,
        context: Optional[str] = None,
        config=None,
        entity_extract_model: str = "Davlan/bert-base-multilingual-cased-ner-hrl",
    ):
        # 调用父类 __init__，将 text 作为 query 传入
        # 父类会设置 self.query = text，NER 管道也用 self.query
        super().__init__(
            llm_client=llm_client,
            query=text,
            config=config,
            entity_extract_model=entity_extract_model,
        )
        # 文档模式特有的上下文信息
        self.context = context

    def _build_extract_prompt(self) -> str:
        """覆盖父类方法 — 构建文档模式的实体抽取 prompt。

        与查询模式 prompt 的关键区别：
            1. 输入是"文档段落"而非"用户问题"
            2. 要求"提取段落中所有实体和关系"，而非"仅提取问题提及的"
            3. 增加上下文信息（标题链、所属法规名），帮助 LLM 理解段落位置
            4. 增加条款号提取指引，与规则辅助抽取配合
        """
        # 复用父类的 NODE_TYPES 和 REL_TYPES（继承的类变量）
        node_desc = "\n".join(f"    - {k}：{v}" for k, v in self.NODE_TYPES.items())
        rel_desc = "\n".join(f"    - {k}：{v}" for k, v in self.REL_TYPES.items())

        # 构建上下文部分（如果有）
        context_section = ""
        if self.context:
            context_section = f"""
## 段落上下文
该段落位于文档的以下层级中：{self.context}
请结合上下文理解段落内容，正确识别实体所属的法规/模块。
"""

        return f"""你是一个消防后勤领域的实体抽取专家。请从以下文档段落中提取所有相关的实体和关系。

## 文档段落
{self.query}
{context_section}
## 图数据库节点类型（仅限以下类型，不得自行编造）
{node_desc}

## 图数据库关系类型（仅限以下类型，不得自行编造）
{rel_desc}

## 抽取规则
1. 提取段落中出现的所有实体和关系，尽可能完整
2. 每个实体的 type 必须是上述节点类型之一，无法确定时选最接近的
3. 关系的 relation 必须是上述关系类型之一，且 source/target 的类型须与关系定义的方向一致
4. 注意识别条款号格式（如 第X条、X.X节、X.X.X条），这些应作为 Clause 类型实体
5. 注意识别法规名称（如《建筑设计防火规范》GB50016），这些应作为 Regulation 类型实体
6. 注意识别设备类型名称（如烟感探测器、喷淋头），这些应作为 EquipmentType 类型实体
7. 如果段落中无法提取出关系，relations 可返回空列表

## 返回格式
严格按照约束格式返回
"""


# ===================== 规则辅助抽取 =====================

def extract_clause_numbers(text: str) -> list[Entity]:
    """从文本中用正则提取条款号，生成 Clause 类型实体。

    识别模式（按优先级排列）：
        - 第X条第X款（中文数字）：如 "第一条第一款"
        - 第X条第X款（阿拉伯数字）：如 "第1条第2款"
        - X.X.X节 / X.X.X条：如 "5.1.1节"、"5.1.1条"
        - X.X节：如 "5.1节"
        - 第X条（中文数字）：如 "第一条"
        - 第X条（阿拉伯数字）：如 "第1条"

    返回的 Entity.type 固定为 "Clause"，
    Entity.name 为匹配到的原始条款号文本。

    Args:
        text: 文档段落文本

    Returns:
        提取到的条款号实体列表（去重后）
    """
    seen = set()       # 去重：避免同一条款号被多个模式重复匹配
    entities = []

    for pattern in CLAUSE_PATTERNS:
        for match in pattern.finditer(text):
            clause_name = match.group()
            if clause_name not in seen:
                seen.add(clause_name)
                entities.append(Entity(name=clause_name, type="Clause"))

    if entities:
        logger.debug(f"规则辅助抽取: 从文本中提取到 {len(entities)} 个条款号")

    return entities


# ===================== 抽取结果校验 =====================

def validate_extract_result(result: ExtractResult) -> ExtractResult:
    """校验抽取结果与 schema.py 的对齐情况。

    校验规则：
        1. 实体 type 必须在 NODE_TYPES 中（EntityExtractor.NODE_TYPES）
        2. 关系 rel_type 必须在 REL_TYPES 中
        3. 移除不合法的实体和关系，记录日志

    Args:
        result: 原始抽取结果

    Returns:
        校验后的抽取结果（可能比输入少）
    """
    valid_node_types = set(EntityExtractor.NODE_TYPES.keys())
    valid_rel_types = set(EntityExtractor.REL_TYPES.keys())

    # 过滤不合法的实体
    valid_entities = []
    for entity in result.entities:
        if entity.type in valid_node_types:
            valid_entities.append(entity)
        else:
            logger.warning(f"校验移除实体: name={entity.name!r}, type={entity.type!r} (不在 NODE_TYPES 中)")

    # 过滤不合法的关系
    valid_relations = []
    for relation in result.relations:
        if relation.relation in valid_rel_types:
            valid_relations.append(relation)
        else:
            logger.warning(
                f"校验移除关系: source={relation.source!r}, target={relation.target!r}, "
                f"rel={relation.relation!r} (不在 REL_TYPES 中)"
            )

    removed_entities = len(result.entities) - len(valid_entities)
    removed_relations = len(result.relations) - len(valid_relations)

    if removed_entities or removed_relations:
        logger.info(
            f"校验结果: 移除 {removed_entities} 个非法实体, {removed_relations} 个非法关系, "
            f"保留 {len(valid_entities)} 个实体, {len(valid_relations)} 个关系"
        )

    return ExtractResult(entities=valid_entities, relations=valid_relations)


# ===================== Neo4j 批量写入器 =====================

class Neo4jBatchWriter:
    """Neo4j 批量写入器 — 使用 UNWIND + MERGE 批量 upsert 节点和关系。

    写入流程：
        1. write_nodes() — 按实体 type 分组，每组用对应的 MERGE_NODE_CYPHER 模板
        2. write_relations() — 按关系 rel_type 分组，每组用对应的 MERGE_REL_CYPHER 模板

    ⚠️ 关系写入必须在节点写入之后！
        因为 MERGE_REL_CYPHER 用 MATCH 查找起终节点，
        如果节点不存在，关系创建会静默失败（MATCH 匹配不到）。

    Args:
        driver: Neo4jDrivers 实例，默认使用模块级的 N4JD
        batch_size: 每批写入的最大记录数，默认 100
    """

    def __init__(
        self,
        driver: Neo4jDrivers = N4JD,
        batch_size: int = 100,
    ):
        self.driver = driver
        self.batch_size = batch_size

    async def write_nodes(
        self,
        entities: list[Entity],
        extra_props: Optional[dict[str, dict]] = None,
    ) -> int:
        """批量写入节点到 Neo4j。

        处理流程：
            1. 按实体 type 分组（Regulation、Clause、Module 等）
            2. 每组内将实体映射为 Cypher 模板所需的 row 字典
            3. 按 batch_size 分批执行 UNWIND + MERGE

        extra_props 可为特定实体名提供额外属性。
        例如：{"第5.1.1条": {"regulation_name": "消防法", "content": "条款内容..."}}
        这样 Clause 节点就能填充 regulation_name 和 content 字段。

        Args:
            entities: 实体列表
            extra_props: 实体名 → 额外属性字典，可选

        Returns:
            写入的节点总数
        """
        if not entities:
            return 0

        extra_props = extra_props or {}

        # 按实体 type 分组
        groups: dict[str, list[Entity]] = {}
        for entity in entities:
            groups.setdefault(entity.type, []).append(entity)

        total_written = 0

        # 获取异步驱动
        a_driver = await self.driver._get_async_driver()

        for node_type, group_entities in groups.items():
            # 查找对应的 Cypher 模板
            cypher = MERGE_NODE_CYPHER.get(node_type)
            if not cypher:
                logger.warning(f"无 MERGE 模板，跳过节点类型: {node_type}")
                continue

            # 将实体映射为 row 字典
            rows = []
            for entity in group_entities:
                # 基础属性：所有节点都有 name
                row: dict = {"name": entity.name}
                # 合并额外属性（如 regulation_name、content 等）
                if entity.name in extra_props:
                    row.update(extra_props[entity.name])
                rows.append(row)

            # 按 batch_size 分批写入
            async with a_driver.session(database=self.driver.database) as session:
                for batch_start in range(0, len(rows), self.batch_size):
                    batch = rows[batch_start : batch_start + self.batch_size]
                    try:
                        await session.run(cypher, {"rows": batch})
                        total_written += len(batch)
                    except Exception as e:
                        logger.error(f"Neo4j 节点写入失败: type={node_type}, batch={batch_start}: {e}")
                        raise

            logger.debug(f"节点写入: {node_type} × {len(rows)}")

        logger.info(f"节点写入完成: 共 {total_written} 个节点")
        return total_written

    async def write_relations(
        self,
        relations: list[Relation],
        extra_props: Optional[dict[str, dict]] = None,
    ) -> int:
        """批量写入关系到 Neo4j。

        处理流程：
            1. 按关系 rel_type 分组（包含条款、引用、适用法规 等）
            2. 每组内将关系映射为 Cypher 模板所需的 row 字典
            3. 按 batch_size 分批执行 UNWIND + MERGE

        ⚠️ 必须在 write_nodes() 之后调用！
            关系的 MERGE 依赖 MATCH 到起终节点。

        Args:
            relations: 关系列表
            extra_props: 关系标识 → 额外属性字典，可选

        Returns:
            写入的关系总数
        """
        if not relations:
            return 0

        extra_props = extra_props or {}

        # 按关系 rel_type 分组
        groups: dict[str, list[Relation]] = {}
        for relation in relations:
            groups.setdefault(relation.relation, []).append(relation)

        total_written = 0

        # 获取异步驱动
        a_driver = await self.driver._get_async_driver()

        for rel_type, group_relations in groups.items():
            # 查找对应的 Cypher 模板
            cypher = MERGE_REL_CYPHER.get(rel_type)
            if not cypher:
                logger.warning(f"无 MERGE 模板，跳过关系类型: {rel_type}")
                continue

            # 将关系映射为 row 字典
            rows = []
            for relation in group_relations:
                # 关系模板统一需要 source_name 和 target_name
                row: dict = {
                    "source_name": relation.source,
                    "target_name": relation.target,
                }
                # 合并额外属性
                rel_key = f"{relation.source}→{relation.target}"
                if rel_key in extra_props:
                    row.update(extra_props[rel_key])
                rows.append(row)

            # 按 batch_size 分批写入
            async with a_driver.session(database=self.driver.database) as session:
                for batch_start in range(0, len(rows), self.batch_size):
                    batch = rows[batch_start : batch_start + self.batch_size]
                    try:
                        await session.run(cypher, {"rows": batch})
                        total_written += len(batch)
                    except Exception as e:
                        logger.error(f"Neo4j 关系写入失败: type={rel_type}, batch={batch_start}: {e}")
                        raise

            logger.debug(f"关系写入: {rel_type} × {len(rows)}")

        logger.info(f"关系写入完成: 共 {total_written} 条关系")
        return total_written


# ===================== 段落级抽取管线 =====================

async def extract_and_write_paragraph(
    paragraph: str,
    llm_client: ChatOpenAI,
    writer: Neo4jBatchWriter,
    context: Optional[str] = None,
    extractor: Optional[DocumentEntityExtractor] = None,
) -> ExtractResult:
    """对单个段落执行抽取 + 规则补充 + 校验 + Neo4j 写入。

    流程：
        1. DocumentEntityExtractor 抽取（LLM + NER 并行）
        2. 规则辅助抽取（条款号正则）
        3. 合并 LLM+NER+规则结果
        4. 校验结果与 schema 对齐
        5. 批量写入 Neo4j（先节点后关系）

    Args:
        paragraph: 段落文本
        llm_client: LLM 客户端
        writer: Neo4j 批量写入器
        context: 段落上下文（标题链等，如 "消防法 > 第三章 > 第十五条"）
        extractor: 可选的预创建抽取器（复用 NER 模型，避免重复加载）

    Returns:
        最终校验后的抽取结果
    """
    # ── 第 1 步：LLM + NER 并行抽取 ──
    if extractor is not None:
        # 复用已有抽取器：只更新文本和上下文，不重新加载 BERT 模型
        extractor.query = paragraph
        extractor.context = context
        result = await extractor.main_pip()
    else:
        # 创建新的抽取器（会加载 BERT 模型，较慢）
        ext = DocumentEntityExtractor(
            llm_client=llm_client,
            text=paragraph,
            context=context,
        )
        result = await ext.main_pip()

    # ── 第 2 步：规则辅助抽取（条款号正则） ──
    clause_entities = extract_clause_numbers(paragraph)

    # ── 第 3 步：合并规则抽取结果 ──
    # 将正则提取的条款号补充到 LLM+NER 结果中
    # 使用 _is_similar 去重：如果 LLM 已提取了相似条款号，则不重复添加
    if clause_entities:
        existing_names = [e.name for e in result.entities]
        for clause_ent in clause_entities:
            # 检查是否与已有实体相似（如 "第5.1.1条" vs "5.1.1条"）
            if not any(EntityExtractor._is_similar(clause_ent.name, name) for name in existing_names):
                result.entities.append(clause_ent)
                logger.debug(f"规则补充实体: {clause_ent.name} (LLM+NER 未提取)")

    # ── 第 4 步：校验结果与 schema 对齐 ──
    result = validate_extract_result(result)

    # ── 第 5 步：写入 Neo4j（先节点后关系） ──
    # 构建额外属性：从 context 中提取 regulation_name 供 Clause 节点使用
    extra_node_props: dict[str, dict] = {}
    if context:
        # 尝试从标题链中提取法规名（通常是第一个部分）
        # 例如 "消防法 > 第三章 > 第十五条" → regulation_name = "消防法"
        context_parts = context.split(" > ")
        if context_parts:
            regulation_name = context_parts[0]
            # 为所有 Clause 类型实体补充 regulation_name
            for entity in result.entities:
                if entity.type == "Clause" and entity.name not in extra_node_props:
                    extra_node_props[entity.name] = {"regulation_name": regulation_name}

    await writer.write_nodes(result.entities, extra_props=extra_node_props)
    await writer.write_relations(result.relations)

    return result


async def extract_and_write_document(
    paragraphs: list[str],
    llm_client: ChatOpenAI,
    writer: Optional[Neo4jBatchWriter] = None,
    contexts: Optional[list[Optional[str]]] = None,
) -> list[ExtractResult]:
    """对整个文档的多个段落执行抽取 + 写入。

    处理流程：
        1. 创建一个 DocumentEntityExtractor 实例（只加载一次 BERT 模型）
        2. 逐段更新 self.query 和 self.context，调用 main_pip()
        3. 每段抽取后立即写入 Neo4j（增量写入，便于观察进度）

    为什么逐段处理而非一次性处理？
        - 单次 LLM 输入长度有限，长文档需要分段
        - 逐段写入便于观察进度和定位问题
        - MERGE 保证幂等，重复运行不会产生重复数据

    Args:
        paragraphs: 段落文本列表（通常来自 splitter.py 的 text_chunks）
        llm_client: LLM 客户端
        writer: Neo4j 批量写入器，默认创建新实例
        contexts: 各段落的上下文列表，与 paragraphs 一一对应
                  例如 ["消防法 > 第三章 > 第十五条", "消防法 > 第三章 > 第十六条", ...]

    Returns:
        各段落的抽取结果列表
    """
    if not paragraphs:
        return []

    # 创建写入器（如果未提供）
    writer = writer or Neo4jBatchWriter()

    # 创建一个抽取器实例，后续复用（避免每段重新加载 BERT 模型）
    # 用第一段文本初始化，后续逐段更新 self.query
    first_context = contexts[0] if contexts else None
    extractor = DocumentEntityExtractor(
        llm_client=llm_client,
        text=paragraphs[0],
        context=first_context,
    )

    results = []

    for i, paragraph in enumerate(paragraphs):
        context = contexts[i] if contexts and i < len(contexts) else None

        try:
            # 第一段用已创建的 extractor，后续段复用同一个实例
            # extract_and_write_paragraph 内部会更新 extractor.query 和 extractor.context
            result = await extract_and_write_paragraph(
                paragraph=paragraph,
                llm_client=llm_client,
                writer=writer,
                context=context,
                extractor=extractor,  # 复用，不重新加载 BERT
            )
            results.append(result)

            logger.info(
                f"段落 {i+1}/{len(paragraphs)} 处理完成: "
                f"实体={len(result.entities)}, 关系={len(result.relations)}"
            )

        except Exception as e:
            # 单段失败不影响其他段落，记录错误后继续
            logger.error(f"段落 {i+1}/{len(paragraphs)} 处理失败: {e}")
            results.append(ExtractResult(entities=[], relations=[]))

    # 汇总统计
    total_entities = sum(len(r.entities) for r in results)
    total_relations = sum(len(r.relations) for r in results)
    logger.info(
        f"文档处理完成: {len(paragraphs)} 个段落, "
        f"共 {total_entities} 个实体, {total_relations} 条关系"
    )

    return results
