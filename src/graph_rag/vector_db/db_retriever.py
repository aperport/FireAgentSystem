"""
向量检索引擎 — dense / sparse / hybrid 三路检索。

检索策略：
    - dense：PG pgvector 余弦相似度（语义模糊查询）
    - sparse：PG sparsevec SQL 余弦检索（BGE-M3 稀疏向量，
      条款号 / 设备型号等精确关键词）
    - hybrid：dense + sparse 经 rrf_merge() 做 RRF 融合（默认推荐）

⚠️ 已知问题：
    1. 方法均为同步，靠 vector_retriever.search() 用 asyncio.to_thread 包装，
       新增直接调用方需自行包装

待优化：
    - hybrid_search 两路检索可并行（当前串行）
"""

import hashlib

from langchain_core.documents import Document
from pgvector.psycopg2.sparsevec import SparseVector

from graph_rag.ingestion.embedding import encode_query_dense, encode_query_sparse
from graph_rag.vector_db.collections import (
    DENSE_SEARCH_SQL,
    LOAD_SOURCE_CHUNKS_SQL,
    SPARSE_SEARCH_SQL,
    SPARSE_VECTOR_PLACEHOLDER,
    PGVectorManager,
)
from util_tools.logger import get_logger

logger = get_logger(__name__)


def rrf_merge(ranked_list: list[tuple[str, list[Document]]], top_k: int, k: int = 60) -> list[Document]:
    """RRF 融合纯函数（模块级）。

    Reciprocal Rank Fusion: score(d) = Σ_i 1 / (k + best_rank_i(d))

    去重 key：PG id 优先，page_content[:200] hash 兜底。
    同一 id 在同一 source 内多次命中只取最佳 rank 算分一次。

    Args:
        ranked_list: [(来源名, 该来源的排序结果), ...]，如 [("dense", docs), ("sparse", docs)]
        top_k: 返回前 k 个
        k: 平滑常数，默认取 60
    """
    # doc_id -> source_name -> 该 source 内最小 rank（用于算分）
    best_rank_per_source: dict[str, dict[str, int]] = {}
    # doc_id -> source_name -> 该 source 内命中 chunk 次数
    chunk_hits_per_source: dict[str, dict[str, int]] = {}
    # doc_id -> (global_best_rank, source_priority, doc) — 选 canonical doc
    best_doc_info: dict[str, tuple[int, int, Document]] = {}

    for source_priority, (source_name, ranked_docs) in enumerate(ranked_list):
        for rank, doc in enumerate(ranked_docs, start=1):
            # 去重 key：PG id 优先，page_content hash 兜底
            pg_id = doc.metadata.get("id")
            doc_id = (
                str(pg_id)
                if pg_id is not None
                else f"hash::{hashlib.md5(doc.page_content[:200].encode('utf-8')).hexdigest()}"
            )

            if doc_id not in best_rank_per_source:
                best_rank_per_source[doc_id] = {}
                chunk_hits_per_source[doc_id] = {}

            curr_best = best_rank_per_source[doc_id].get(source_name)
            if curr_best is None or rank < curr_best:
                best_rank_per_source[doc_id][source_name] = rank

            chunk_hits_per_source[doc_id][source_name] = chunk_hits_per_source[doc_id].get(source_name, 0) + 1

            new_key = (rank, source_priority)
            if doc_id not in best_doc_info or new_key < (best_doc_info[doc_id][0], best_doc_info[doc_id][1]):
                best_doc_info[doc_id] = (rank, source_priority, doc)

    # 每个 source 只用 best rank 算一次贡献
    rrf_scores: dict[str, float] = {
        doc_id: sum(1.0 / (k + r) for r in source_ranks.values())
        for doc_id, source_ranks in best_rank_per_source.items()
    }

    sorted_ids = sorted(rrf_scores.keys(), key=lambda d: rrf_scores[d], reverse=True)

    merged: list[Document] = []
    for doc_id in sorted_ids[:top_k]:
        _, _, source_doc = best_doc_info[doc_id]
        new_metadata = dict(source_doc.metadata)
        new_metadata["rrf_score"] = rrf_scores[doc_id]
        new_metadata["rrf_sources"] = list(best_rank_per_source[doc_id].keys())
        new_metadata["rrf_ranks"] = dict(best_rank_per_source[doc_id])
        new_metadata["rrf_chunk_hits"] = dict(chunk_hits_per_source[doc_id])
        new_metadata["final_score"] = rrf_scores[doc_id]
        merged.append(
            Document(
                page_content=source_doc.page_content,
                metadata=new_metadata,
            )
        )

    return merged


class HybridRetrievalModule:
    """混合检索模块 — 只负责三路检索与融合，不管模型、不管上下文组装。

    1. 稠密检索（pgvector 余弦相似度，BGE-M3 dense）
    2. 稀疏检索（pgvector sparsevec 余弦，BGE-M3 sparse）
    3. RRF 融合多路检索结果（模块级 rrf_merge 纯函数）
    """

    def __init__(self, pg: "PGVectorManager"):
        """初始化混合检索模块。

        Args:
            pg: PGVectorManager 连接管理器（仅提供 cursor，不含模型）。
                查询向量化走 ingestion.embedding.encode_query_dense()，
                与入库向量化同一模型、同一向量空间。
        """
        self.pg = pg

    def load_source_chunks(self, source_file: str) -> list[Document]:
        """按需加载某 source_file 的全部 chunk（按入库顺序，即 id 升序）。

        父文档回填使用：命中 chunk 后现场从 PG 拉同源邻居，避免全表加载。
        source_file 列存的是来源文件 hash（collections.FIRE_DOC_DDL），
        同一文件的所有 chunk 共享同一 hash，故可按此分组。

        Args:
            source_file: 来源文件 hash

        Returns:
            list[Document]: 同源全部 chunk，metadata 含 id/category/source_file/source_name/title
        """
        try:
            cur = self.pg.get_cursor()
            cur.execute(LOAD_SOURCE_CHUNKS_SQL, (source_file,))
            rows = cur.fetchall()
            docs = [
                Document(
                    page_content=row["text"],
                    metadata={
                        "id": row["id"],
                        "category": row["category"],
                        "source_file": row["source_file"],
                        "source_name": row.get("source_name", ""),
                        "title": row["title"],
                        "search_type": "parent_fill",
                    },
                )
                for row in rows
            ]
            logger.info(f"按需加载同源 chunk：source_file={source_file}，共 {len(docs)} 条")
            return docs
        except Exception as e:
            logger.error(f"按需加载同源 chunk 失败：source_file={source_file}，错误={e}")
            return []

    def _query_sparse_vector(self, query: str, max_sparse_tokens: int = 128) -> SparseVector:
        """查询文本 → pgvector SparseVector。

        与入库侧 db_operator 同规则：BGE-M3 lexical_weights 按权重
        Top-128 截断（sparsevec HNSW 索引非零元素上限 1000），
        token id +1（sparsevec 索引从 1 起），总维度 250002。
        """
        sparse = encode_query_sparse(query)
        top_items = sorted(sparse.items(), key=lambda x: x[1], reverse=True)[:max_sparse_tokens]
        return SparseVector({k + 1: v for k, v in top_items}, 250002)

    def sparse_search(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
        score_threshold: float = 0.1,
        table_name: str = "fire_doc_collection",
    ) -> list[Document]:
        """稀疏向量检索（PG pgvector sparsevec 余弦相似度）。

        查询文本经 BGE-M3 稀疏向量化后，与库内 sparse_vector 做
        余弦距离检索。

        Args:
            query: 查询文本
            top_k: 返回前 k 个结果
            category: 按分类过滤，None 表示不过滤
            score_threshold: 最低相似度阈值，低于此值的结果将被过滤
            table_name: 查询的表名，默认 fire_doc_collection

        Returns:
            list[Document]: 检索结果列表，metadata 中包含 score 和 search_type
        """
        query_sparse_vec = self._query_sparse_vector(query)

        category_filter = "AND category = %s" if category else ""
        sql = SPARSE_SEARCH_SQL.format(
            table_name=table_name,
            sparse_vector_placeholder=SPARSE_VECTOR_PLACEHOLDER,
            category_filter=category_filter,
        )

        cur = self.pg.get_cursor()
        if category:
            cur.execute(sql, (query_sparse_vec, category, query_sparse_vec, top_k))
        else:
            cur.execute(sql, (query_sparse_vec, query_sparse_vec, top_k))

        docs: list[Document] = []
        for row in cur.fetchall():
            score = float(row["score"])
            if score < score_threshold:
                continue
            docs.append(
                Document(
                    page_content=row["text"],
                    metadata={
                        "id": row["id"],
                        "category": row["category"],
                        "source_file": row["source_file"],
                        "title": row["title"],
                        "source_name": row.get("source_name", ""),
                        "score": score,
                        "search_type": "sparse",
                    },
                )
            )
            logger.info(f"Sparse 检索结果：{row['text'][:80]}...，分数：{score:.4f}")
        return docs

    def dense_search(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
        score_threshold: float = 0.1,
        table_name: str = "fire_doc_collection",
    ) -> list[Document]:
        """稠密向量检索（PG pgvector 余弦相似度）

        通过 Embedding 将查询文本向量化，然后在 PostgreSQL 中使用
        pgvector 的余弦距离操作符 <=> 进行相似度检索。

        Args:
            query: 查询文本
            top_k: 返回前 k 个结果
            category: 按分类过滤（regulation / standard / manual / faq），None 表示不过滤
            score_threshold: 最低相似度阈值，低于此值的结果将被过滤
            table_name: 查询的表名，默认 fire_doc_collection

        Returns:
            list[Document]: 检索结果列表，metadata 中包含 score 和 search_type
        """
        try:
            # 1. 查询文本向量化（全局 Embedding 单例，与入库同一模型）
            query_vector = encode_query_dense(query)

            # 2. 构建分类过滤条件
            category_filter = ""
            if category:
                category_filter = "AND category = %s"

            # 3. 组装 SQL
            sql = DENSE_SEARCH_SQL.format(
                table_name=table_name,
                category_filter=category_filter,
            )

            # 4. 执行查询（pgvector 余弦距离：向量参数传两次，一次算分数，一次排序）
            cur = self.pg.get_cursor()
            if category:
                cur.execute(sql, (query_vector, category, query_vector, top_k))
            else:
                cur.execute(sql, (query_vector, query_vector, top_k))

            rows = cur.fetchall()

            # 5. 转换为 Document 列表
            docs: list[Document] = []
            for row in rows:
                score = float(row["score"])
                if score < score_threshold:
                    continue
                doc = Document(
                    page_content=row["text"],
                    metadata={
                        "id": row["id"],
                        "category": row["category"],
                        "source_file": row["source_file"],
                        "title": row["title"],
                        "source_name": row.get("source_name", ""),
                        "score": score,
                        "search_type": "dense",
                    },
                )
                docs.append(doc)
                logger.info(f"Dense 检索结果：{doc.page_content[:80]}...，分数：{score:.4f}")

            return docs

        except Exception as e:
            logger.error(f"稠密向量检索失败：{e}")
            return []

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
        score_threshold: float = 0.1,
        rrf_k: int = 60,
    ) -> list[Document]:
        """混合检索（dense + sparse RRF 融合）

        同时执行稠密向量检索和稀疏向量检索，然后使用
        Reciprocal Rank Fusion (RRF) 融合两路结果，兼顾语义和关键词匹配。

        Args:
            query: 查询文本
            top_k: 最终返回前 k 个结果
            category: 按分类过滤
            score_threshold: 最低相似度阈值
            rrf_k: RRF 平滑常数，默认 60

        Returns:
            list[Document]: RRF 融合后的检索结果
        """
        # 1. 执行两路检索（各取 top_k * 2 扩大候选集，两路统一分类过滤）
        expand_k = top_k * 2
        dense_docs = self.dense_search(query, top_k=expand_k, category=category, score_threshold=score_threshold)
        sparse_docs = self.sparse_search(query, top_k=expand_k, category=category, score_threshold=score_threshold)

        # 2. RRF 融合（模块级纯函数）
        ranked_list: list[tuple[str, list[Document]]] = [
            ("dense", dense_docs),
            ("sparse", sparse_docs),
        ]
        merged = rrf_merge(ranked_list, top_k=top_k, k=rrf_k)

        # 标记检索类型
        for doc in merged:
            doc.metadata["search_type"] = "hybrid"

        logger.info(f"Hybrid 检索完成：dense={len(dense_docs)}, sparse={len(sparse_docs)}, 融合后={len(merged)}")
        return merged
