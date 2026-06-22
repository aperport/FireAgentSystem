"""
向量数据插入模块 — 将向量化后的文档片段写入 PostgreSQL + pgvector 向量表。

支持的写入场景：
    1. 知识文档入库：doc_parser + splitter + embedding → fire_doc_collection
    2. 图片文档入库：图片提取 + 多模态描述 → fire_image_collection(文本来自于OCR或者多模态对图像的描述，可以不用分块)

数据来源：
    - ingestion/doc_parser.py 解析后的 Markdown 文本
    - ingestion/embedding.py 生成的向量

写入格式遵循 collections.py 中定义的表 Schema。
数据入库后需调用 PGVectorManager.build_vector_indexes() 构建向量索引，
以及 db_retriever.rebuild_bm25_index() 重建 BM25 索引。
"""

import os
from langchain_core.documents import Document
from graph_rag.vector_db.collections import PGVectorManager
from unitl_tools.logger import get_logger

logger = get_logger(__name__)

# PG 连接参数从环境变量读取，不再硬编码
_PG_HOST = os.getenv("PG_HOST", "localhost")
_PG_PORT = int(os.getenv("PG_PORT", "5432"))
_PG_USER = os.getenv("PG_USER", "postgres")
_PG_PASSWORD = os.getenv("PG_PASSWORD", "")
_PG_DBNAME = os.getenv("PG_DBNAME", "fire_rag")


class DBOperator:
    """向量数据操作器 — 延迟初始化 PGVectorManager"""

    def __init__(self):
        self._pg: PGVectorManager | None = None

    @property
    def pg(self) -> PGVectorManager:
        """延迟初始化 PGVectorManager，首次访问时创建连接"""
        if self._pg is None:
            if not _PG_PASSWORD:
                raise ValueError(
                    "PG_PASSWORD 环境变量未设置，请在 .env 中配置 PostgreSQL 密码"
                )
            self._pg = PGVectorManager(
                host=_PG_HOST,
                user=_PG_USER,
                password=_PG_PASSWORD,
                dbname=_PG_DBNAME,
                port=_PG_PORT,
            )
            logger.info(f"PGVectorManager 已初始化: {_PG_HOST}:{_PG_PORT}/{_PG_DBNAME}")
        return self._pg

    def insert_chunks(self, chunks: list[Document]) -> None:
        """
        将向量化后的文档片段写入 PostgreSQL + pgvector 向量表。
        """
        try:
            if chunks:
                texts = [chunk.page_content for chunk in chunks]
                vectors = self.pg.embeddings.embed_documents(texts)  # type: ignore
                logger.info(f"向量表 fire_doc_collection 写入 {len(texts)} 条数据")
                # 将向量化后的文档片段写入 PostgreSQL + pgvector 向量表
                insert_sql = """
                INSERT INTO  fire_doc_collection (text, category, source_file,source_name, title, dense_vector)
                VALUES (%s, %s, %s, %s, %s, %s);
                """
                # 对应取出数据
                cur = self.pg.get_cursor()
                for chunk, vector in zip(chunks, vectors):
                    cur.execute(insert_sql, (chunk.page_content, chunk.metadata.get("category", ""), chunk.metadata.get("source_file", ""), chunk.metadata.get("title", ""), vector))
                logger.info(f"向量表 fire_doc_collection 写入完成，共 {len(texts)} 条数据")
        except Exception as e:
            logger.error(f"向量表 fire_doc_collection 写入失败：{e}")
            raise


    def insert_picture(self, documents: list[Document]) -> None:
        """
        将向量化的图片描述写入 PostgreSQL + pgvector 向量表。
        图片描述文本来自 OCR 或多模态模型对图像的描述，无需分块，整条写入。
        """
        try:
            if documents:
                texts = [doc.page_content for doc in documents]
                vectors = self.pg.embeddings.embed_documents(texts)  # type: ignore
                logger.info(f"向量表 fire_image_collection 写入 {len(texts)} 条数据")
                insert_sql = """
                INSERT INTO fire_image_collection (text, category, image_path, source_file, source_name, title, dense_vector)
                VALUES (%s, %s, %s, %s, %s, %s, %s);
                """
                cur = self.pg.get_cursor()
                for doc, vector in zip(documents, vectors):
                    cur.execute(insert_sql, (
                        doc.page_content,
                        doc.metadata.get("category", ""),
                        doc.metadata.get("image_path", ""),
                        doc.metadata.get("source_file", ""),
                        doc.metadata.get("title", ""),
                        vector,
                    ))
                logger.info(f"向量表 fire_image_collection 写入完成，共 {len(texts)} 条数据")
        except Exception as e:
            logger.error(f"向量表 fire_image_collection 写入失败：{e}")
            raise
