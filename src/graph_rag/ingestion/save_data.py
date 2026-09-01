import sys
from pathlib import Path

# ponytail: 测试脚本，手动把 src/ 加入搜索路径
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))


from dataclasses import dataclass
from typing import Optional

from langchain_core.language_models import BaseChatModel

from graph_rag.graph_db.writer import Neo4jBatchWriter
from graph_rag.ingestion.doc_parser.md_parser import MdParser
from graph_rag.ingestion.entity_relation_extractor import extract_and_write_document
from graph_rag.ingestion.splitter import split
from graph_rag.vector_db.db_operator import DBOperator
from util_tools.logger import get_logger

logger = get_logger(__name__)


# ─── 入库结果 ───

@dataclass
class IngestResult:
    """单个文档的入库结果。"""
    file_path: str
    success: bool
    text_chunks: int = 0
    image_docs: int = 0
    entities: int = 0
    relations: int = 0
    error: str = ""


# ─── 顶层编排 ───

async def ingest_markdown(
    file_path: str,
    llm_client: Optional[BaseChatModel] = None,
    writer: Optional[Neo4jBatchWriter] = None,
) -> IngestResult:
    """将单个 Markdown 文件完整入库（PG 向量 + Neo4j 图谱）。

    自动执行：解析 → 切分 → PG写入 → 实体抽取 → Neo4j写入

    Args:
        file_path: Markdown 文件路径
        llm_client: LLM 客户端，必须由调用方注入
        writer: Neo4j 批量写入器，None 则自动创建
    """
    if llm_client is None:
        raise ValueError("llm_client 不能为空，请由调用方注入 LLM 实例")

    try:
        # 1. 解析
        parsed = MdParser().parse(file_path)

        # 2. 切分
        text_chunks, image_docs = split(parsed)

        # 3. PG 向量写入
        db_op = DBOperator()
        if text_chunks:
            db_op.insert_chunks(text_chunks)
        if image_docs:
            db_op.insert_picture(image_docs)

        # 4. Neo4j 实体/关系写入
        # ponytail: 用 text_chunks 的 page_content 作为段落，保留 header_chain 上下文
        paragraphs = [c.page_content for c in text_chunks]
        contexts = [c.metadata.get("header_chain") for c in text_chunks]

        neo4j_writer = writer or Neo4jBatchWriter()
        extract_results = await extract_and_write_document(
            paragraphs=paragraphs,
            llm_client=llm_client,
            writer=neo4j_writer,
            contexts=contexts,
        )

        total_entities = sum(len(r.entities) for r in extract_results)
        total_relations = sum(len(r.relations) for r in extract_results)

        logger.info(
            f"入库完成: {file_path}, 文本={len(text_chunks)}, "
            f"图片={len(image_docs)}, 实体={total_entities}, 关系={total_relations}"
        )
        return IngestResult(
            file_path=file_path,
            success=True,
            text_chunks=len(text_chunks),
            image_docs=len(image_docs),
            entities=total_entities,
            relations=total_relations,
        )

    except Exception as e:
        logger.error(f"入库失败: {file_path}: {e}")
        return IngestResult(file_path=file_path, success=False, error=str(e))


async def ingest_directory(
    dir_path: str,
    llm_client: Optional[BaseChatModel] = None,
) -> list[IngestResult]:
    """将目录下所有 Markdown 文件批量入库。

    复用同一个 LLM 客户端和 Neo4j 写入器，避免重复初始化。

    Args:
        dir_path: 目录路径
        llm_client: LLM 客户端，必须由调用方注入
    """
    if llm_client is None:
        raise ValueError("llm_client 不能为空，请由调用方注入 LLM 实例")

    writer = Neo4jBatchWriter()
    parsed_docs = MdParser().parse_directory(dir_path)

    results: list[IngestResult] = []
    for parsed in parsed_docs:
        file_path = parsed.metadata.get("source", "")
        try:
            text_chunks, image_docs = split(parsed)

            db_op = DBOperator()
            if text_chunks:
                db_op.insert_chunks(text_chunks)
            if image_docs:
                db_op.insert_picture(image_docs)

            paragraphs = [c.page_content for c in text_chunks]
            contexts = [c.metadata.get("header_chain") for c in text_chunks]

            extract_results = await extract_and_write_document(
                paragraphs=paragraphs,
                llm_client=llm_client,
                writer=writer,
                contexts=contexts,
            )

            total_entities = sum(len(r.entities) for r in extract_results)
            total_relations = sum(len(r.relations) for r in extract_results)

            results.append(IngestResult(
                file_path=file_path, success=True,
                text_chunks=len(text_chunks), image_docs=len(image_docs),
                entities=total_entities, relations=total_relations,
            ))

        except Exception as e:
            logger.error(f"入库失败: {file_path}: {e}")
            results.append(IngestResult(file_path=file_path, success=False, error=str(e)))

    ok = sum(1 for r in results if r.success)
    logger.info(f"目录入库完成: {dir_path}, 成功={ok}/{len(results)}")
    return results
