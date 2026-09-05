"""
实体/关系抽取模块 — 从文档段落中抽取实体和关系写入 Neo4j。

抽取方式：LLM 结构化输出 + NER 小模型补充 + 条款号正则辅助。

写入和校验复用 graph_db 子模块：
    - Neo4jBatchWriter / MERGE 模板 → graph_db.writer
    - NODE_TYPES / REL_TYPES        → graph_db.schema
    - validate_extract_result       → 本模块（见文件末尾）
"""

import re
from typing import Optional

from langchain_openai import ChatOpenAI

from graph_rag.entity_extractor import Entity, ExtractResult
from graph_rag.graph_db.writer import Neo4jBatchWriter
from graph_rag.graph_db.schema import NODE_TYPES, REL_TYPES
from util_tools.logger import get_logger

logger = get_logger(__name__)


# ===================== 条款号正则模式 =====================
# 按优先级排列：最具体的模式在前，避免被宽泛模式提前匹配
CLAUSE_PATTERNS: list[re.Pattern] = [
    re.compile(r"第[一二三四五六七八九十百千]+条第[一二三四五六七八九十]+款"),  # 第X条第X款（中文）
    re.compile(r"第\d+条第\d+款"),                                              # 第X条第X款（阿拉伯）
    re.compile(r"\d+\.\d+(?:\.\d+)?(?:节|条)"),                                 # X.X.X节/条
    re.compile(r"\d+\.\d+节"),                                                   # X.X节
    re.compile(r"第[一二三四五六七八九十百千]+条"),                              # 第X条（中文）
    re.compile(r"第\d+条"),                                                      # 第X条（阿拉伯）
]


# ===================== 文档模式实体抽取器 =====================

class DocumentEntityExtractor():
    """文档模式实体抽取器 — 覆盖 prompt 为文档抽取模式。
    """

    def __init__(
        self,
        llm_client: ChatOpenAI,
        text: str,
        context: str | None = None,
        config=None,
        entity_extract_model: str = "Davlan/bert-base-multilingual-cased-ner-hrl",
    ):
        super().__init__(
            llm_client=llm_client,
            query=text,
            config=config,
            entity_extract_model=entity_extract_model,
        )
        self.context = context

    def _build_extract_prompt(self) -> str:
        """覆盖父类方法 — 构建文档模式的实体抽取 prompt。"""
        node_desc = "\n".join(f"    - {k}：{v}" for k, v in self.NODE_TYPES.items())
        rel_desc = "\n".join(f"    - {k}：{v}" for k, v in self.REL_TYPES.items())

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
请严格返回如下 JSON 格式，不要输出任何其他内容：
```json
{{
  "entities": [{{"name": "实体名", "type": "节点类型"}}],
  "relations": [{{"source": "源实体名", "target": "目标实体名", "relation": "关系类型"}}]
}}
```
"""


# ===================== 规则辅助抽取 =====================

def extract_clause_numbers(text: str) -> list[Entity]:
    """从文本中用正则提取条款号，生成 Clause 类型实体。"""
    seen = set()
    entities = []
    for pattern in CLAUSE_PATTERNS:
        for match in pattern.finditer(text):
            name = match.group()
            if name not in seen:
                seen.add(name)
                entities.append(Entity(name=name, type="Clause"))
    if entities:
        logger.debug(f"规则辅助抽取: 从文本中提取到 {len(entities)} 个条款号")
    return entities


# ===================== 段落级抽取管线 =====================

async def extract_and_write_paragraph(
    paragraph: str,
    llm_client: ChatOpenAI,
    writer: Neo4jBatchWriter,
    context: Optional[str] = None,
    extractor: Optional[DocumentEntityExtractor] = None,
) -> ExtractResult:
    """对单个段落执行抽取 + 规则补充 + 校验 + Neo4j 写入。

    流程：LLM+NER 并行 → 条款号正则补充 → schema 校验 → 批量写入
    """
    # 1. LLM + NER 并行抽取
    if extractor is not None:
        extractor.query = paragraph
        extractor.context = context
        result = await extractor.main_pip()
    else:
        ext = DocumentEntityExtractor(llm_client=llm_client, text=paragraph, context=context)
        result = await ext.main_pip()

    # 2. 规则辅助抽取（条款号正则）
    clause_entities = extract_clause_numbers(paragraph)

    # 3. 合并，用 _is_similar 去重
    if clause_entities:
        existing_names = [e.name for e in result.entities]
        for ent in clause_entities:
            if not any(EntityExtractor._is_similar(ent.name, n) for n in existing_names):
                result.entities.append(ent)
                logger.debug(f"规则补充实体: {ent.name} (LLM+NER 未提取)")

    # 4. schema 校验
    result = validate_extract_result(result)

    # 5. 写入 Neo4j（先节点后关系）
    extra_node_props: dict[str, dict] = {}
    if context:
        regulation_name = context.split(" > ")[0]
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

    复用单个 DocumentEntityExtractor 实例（只加载一次 BERT 模型），
    逐段更新 self.query，每段抽取后立即写入。
    """
    if not paragraphs:
        return []

    writer = writer or Neo4jBatchWriter()

    first_context = contexts[0] if contexts else None
    extractor = DocumentEntityExtractor(
        llm_client=llm_client, text=paragraphs[0], context=first_context,
    )

    results = []
    for i, paragraph in enumerate(paragraphs):
        context = contexts[i] if contexts and i < len(contexts) else None
        try:
            result = await extract_and_write_paragraph(
                paragraph=paragraph, llm_client=llm_client,
                writer=writer, context=context, extractor=extractor,
            )
            results.append(result)
            logger.info(f"段落 {i+1}/{len(paragraphs)}: 实体={len(result.entities)}, 关系={len(result.relations)}")
        except Exception as e:
            logger.error(f"段落 {i+1}/{len(paragraphs)} 处理失败: {e}")
            results.append(ExtractResult(entities=[], relations=[]))

    total_entities = sum(len(r.entities) for r in results)
    total_relations = sum(len(r.relations) for r in results)
    logger.info(f"文档处理完成: {len(paragraphs)} 段, {total_entities} 实体, {total_relations} 关系")

    return results


# ──────────────── 抽取结果校验 ────────────────

def validate_extract_result(result: "ExtractResult") -> "ExtractResult":
    """校验抽取结果与 schema 的对齐情况。

    校验规则：
        1. 实体 type 必须在 NODE_TYPES 中
        2. 关系 rel_type 必须在 REL_TYPES 中
        3. 移除不合法的实体和关系，记录日志

    Args:
        result: 原始抽取结果

    Returns:
        校验后的抽取结果（可能比输入少）
    """

    valid_node_types = set(NODE_TYPES.keys())
    valid_rel_types = set(REL_TYPES.keys())

    valid_entities = []
    for entity in result.entities:
        if entity.type in valid_node_types:
            valid_entities.append(entity)
        else:
            logger.warning(f"校验移除实体: name={entity.name!r}, type={entity.type!r} (不在 NODE_TYPES 中)")

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
