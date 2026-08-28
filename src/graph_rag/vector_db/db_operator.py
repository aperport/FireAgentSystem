"""
向量数据插入模块 — 将向量化后的文档片段写入 PostgreSQL + pgvector 向量表。

✅ 已实现。支持的写入场景：
    1. 知识文档入库：doc_parser + splitter + embedding → fire_doc_collection
    2. 图片文档入库：图片提取 + 多模态描述 → fire_image_collection
       （文本来自 OCR 或多模态对图像的描述，可以不用分块）

已实现方法：
    - insert_chunks()    批量写入文本片段（含向量）到 fire_doc_collection
    - insert_picture()   批量写入图片描述（含向量）到 fire_image_collection

数据来源：
    - ingestion/doc_parser/ 解析后的文本
    - ingestion/embedding.py（❌ 骨架）生成的向量

写入格式遵循 collections.py 中定义的表 Schema。
数据入库后需调用 PGVectorManager.build_vector_indexes() 构建向量索引，
以及 db_retriever.rebuild_bm25_index() 重建 BM25 索引。


待优化：
    - 使用批量写入（executemany / copy_from）提升入库性能
    - 增加写入去重：相同 source_file + title 的文档不重复写入
"""

import os
from langchain_core.documents import Document
from graph_rag.config import get_settings
from graph_rag.vector_db.collections import PGVectorManager, get_pg_instance
from util_tools.logger import get_logger

logger = get_logger(__name__)


class DBOperator:
    """向量数据操作器 — 延迟初始化 PGVectorManager"""

    def __init__(self):
        self._pg: PGVectorManager | None = None

    @property
    def pg(self) -> PGVectorManager:
        """延迟初始化 PGVectorManager，首次访问时创建连接"""
        if self._pg is None:
            s = get_settings()
            if not s.pg_password:
                raise ValueError(
                    "PG_PASSWORD 环境变量未设置，请在 .env 中配置 PostgreSQL 密码"
                )
            self._pg = get_pg_instance(
                host=s.pg_host,
                user=s.pg_user,
                password=s.pg_password,
                dbname=s.pg_dbname,
                port=s.pg_port,
            )
            logger.info(f"PGVectorManager 已初始化: {s.pg_host}:{s.pg_port}/{s.pg_dbname}")
        return self._pg

    # [合并理由] insert_chunks 和 insert_picture 逻辑几乎完全相同，
    # 只有表名和字段不同。提取公共方法 _insert_documents() 减少重复代码。
    def _insert_documents(
        self,
        table_name: str,
        columns: list[str],
        documents: list[Document],
        metadata_keys: list[str],
    ) -> None:
        """通用向量文档写入方法。

        Args:
            table_name: 目标表名（如 fire_doc_collection / fire_image_collection）
            columns: 列名列表（最后一列必须是 dense_vector）
            documents: 待写入的文档列表
            metadata_keys: 从 metadata 中提取的字段名列表（与 columns 前 N-1 列对应，不含 text 和 dense_vector）
        """
        if not documents:
            return
        try:
            texts = [doc.page_content for doc in documents]
            vectors = self.pg.embeddings.embed_documents(texts)  # type: ignore
            logger.info(f"向量表 {table_name} 写入 {len(texts)} 条数据")

            col_str = ", ".join(columns)
            placeholders = ", ".join(["%s"] * len(columns))
            insert_sql = f"INSERT INTO {table_name} ({col_str}) VALUES ({placeholders});"

            cur = self.pg.get_cursor()
            for doc, vector in zip(documents, vectors):
                values = [doc.page_content]
                for key in metadata_keys:
                    values.append(doc.metadata.get(key, ""))
                values.append(vector)
                cur.execute(insert_sql, tuple(values))
            logger.info(f"向量表 {table_name} 写入完成，共 {len(texts)} 条数据")
        except Exception as e:
            logger.error(f"向量表 {table_name} 写入失败：{e}")
            raise

    def insert_chunks(self, chunks: list[Document]) -> None:
        """将向量化后的文档片段写入 fire_doc_collection。"""
        self._insert_documents(
            table_name="fire_doc_collection",
            columns=["text", "category", "source_file", "source_name", "title", "dense_vector"],
            documents=chunks,
            metadata_keys=["category", "source_file", "source_name", "title"],
        )

    def insert_picture(self, documents: list[Document]) -> None:
        """将向量化的图片描述写入 fire_image_collection。"""
        self._insert_documents(
            table_name="fire_image_collection",
            columns=["text", "category", "image_path", "source_file", "source_name", "title", "dense_vector"],
            documents=documents,
            metadata_keys=["category", "image_path", "source_file", "source_name", "title"],
        )
