"""
实体/关系抽取模块 — 从文档段落中抽取实体和关系写入 Neo4j。

抽取方式：LLM 结构化输出 + NER 小模型补充

写入和校验复用 graph_db 子模块：
    - Neo4jBatchWriter / MERGE 模板 → graph_db.writer
    - NODE_TYPES / REL_TYPES        → graph_db.schema
    - validate_extract_result       → 本模块（见文件末尾）
"""

import asyncio

from graph_rag.entity_extractor import DocumentGraphExtractionPipeline, ExtractResult, LlmEntityExtractor
from graph_rag.graph_db.writer import Neo4jBatchWriter
from util_tools.logger import get_logger

logger = get_logger(__name__)


class LlmEntityExtractorByDOC(LlmEntityExtractor):
    def _build_extract_prompt(self, paragraph: str, context: str | None = None) -> str:
        """
        构建实体抽取 prompt，将图 Schema 约束嵌入其中。
        此处提示词需要修改
        """
        node_desc, rel_desc = self._format_schema()
        context_section = ""
        if context:
            context_section = f"""
        ## 段落上下文
        该段落位于文档的以下层级中：{context}
        请结合上下文理解段落内容，正确识别实体所属的模块/范畴。
        """
        return f"""你是一个专业领域的实体抽取专家。请从以下文档段落中提取所有相关的实体和关系。

        ## 文档段落
        {paragraph}
        {context_section}
        ## 图数据库节点类型（仅限以下类型，不得自行编造）
        {node_desc}

        ## 图数据库关系类型（仅限以下类型，不得自行编造）
        {rel_desc}

        ## 抽取规则
        1. 提取段落中出现的所有实体和关系，尽可能完整
        2. 每个实体的 type 必须是上述节点类型之一，无法确定时选最接近的
        3. 关系的 relation 必须是上述关系类型之一，且 source/target 的类型须与关系定义的方向一致
        4. 如果段落中无法提取出关系，relations 可返回空列表
        5. 不要输出与段落内容无关的实体

        ## 返回格式
        请严格返回如下 JSON 格式，不要输出任何其他内容：
        ```json
        {{
        "entities": [{{"name": "实体名", "type": "节点类型"}}],
        "relations": [{{"source": "源实体名", "target": "目标实体名", "relation": "关系类型"}}]
        }}
        """


class DocumentGraphPipeline:
    """
    通用文档图数据抽取与落库流水线（长生命周期、无状态、可复用）。
    负责：LLM+NER并发 -> 规则补充 -> Schema过滤 -> 属性组装 -> Neo4j持久化。
    """

    def __init__(self, extraction_pipeline: DocumentGraphExtractionPipeline, writer: Neo4jBatchWriter) -> None:
        self.writer = writer
        self.extraction_pipeline = extraction_pipeline

    async def process_paragraph(self, paragraph: str, context: str | None = None) -> ExtractResult:
        """
        抽取实体和关系，写入 Neo4j
        """
        result = await self.extraction_pipeline.extract(paragraph, context=context)

        # 类型关系校验 提示词要求选择已有关系，但依然可能捏造，所以进行一步校验（）

        # 写入neo4j

        if getattr(result, "entities", []):
            await self.writer.write_nodes(result.entities)
        if getattr(result, "relations", []):
            await self.writer.write_relations(result.relations)
        return result

    async def process_document(
        self,
        paragraphs: list[str],
        contexts: list[str | None] | None = None,
        max_concurrency: int = 3,
    ) -> list[ExtractResult]:
        """多段落文档级受控并发调度。"""
        if not paragraphs:
            return []

        # 用信号量控制 LLM 并发，避免触发 API 限流
        sem = asyncio.Semaphore(max_concurrency)

        async def _worker(idx: int, p: str):
            ctx = contexts[idx] if contexts and idx < len(contexts) else None
            async with sem:
                try:
                    res = await self.process_paragraph(p, context=ctx)
                    logger.info(
                        "段落 %d/%d 处理成功: 实体=%d, 关系=%d",
                        idx + 1,
                        len(paragraphs),
                        len(res.entities),
                        len(res.relations),
                    )
                    return res
                except Exception as e:
                    logger.error("段落 %d/%d 处理异常: %s", idx + 1, len(paragraphs), e)
                    return ExtractResult(entities=[], relations=[])

        tasks = [_worker(i, p) for i, p in enumerate(paragraphs)]
        results = await asyncio.gather(*tasks)

        total_entities = sum(len(r.entities) for r in results)
        total_relations = sum(len(r.relations) for r in results)
        logger.info(
            "文档全量写入完毕: 共 %d 个段落, 写入 %d 实体, %d 关系", len(paragraphs), total_entities, total_relations
        )
        return list(results)
