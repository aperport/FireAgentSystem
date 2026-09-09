"""
向量检索引擎单元测试（db_retriever.py）

测试覆盖：
    1. rrf_merge — RRF 融合纯函数
    2. HybridRetrievalModule.dense_search — 稠密检索（mock PG + embedding）
    3. HybridRetrievalModule.sparse_search — 稀疏检索（mock PG）
    4. HybridRetrievalModule.hybrid_search — 混合检索
    5. HybridRetrievalModule.load_source_chunks — 同源 chunk 加载
"""

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.documents import Document

from graph_rag.vector_db.db_retriever import HybridRetrievalModule, rrf_merge


def make_doc(content: str, **metadata) -> Document:
    return Document(page_content=content, metadata=metadata)


def make_cursor(rows: list[dict]) -> MagicMock:
    cur = MagicMock()
    cur.fetchall.return_value = rows
    return cur


class TestRrfMerge:
    """RRF 融合纯函数测试"""

    def test_rank_dependent_scoring(self):
        """同时出现在两路的文档分数最高，排在首位"""
        dense = [make_doc("A", id=1), make_doc("B", id=2)]
        sparse = [make_doc("B", id=2), make_doc("C", id=3)]
        merged = rrf_merge([("dense", dense), ("sparse", sparse)], top_k=3)
        # B：dense rank2(1/62) + sparse rank1(1/61)；A：1/61；C：1/62
        assert merged[0].metadata["id"] == 2
        assert merged[0].metadata["rrf_score"] == pytest.approx(1 / 61 + 1 / 62)
        assert merged[1].metadata["id"] == 1

    def test_rrf_metadata_attached(self):
        dense = [make_doc("A", id=1)]
        merged = rrf_merge([("dense", dense)], top_k=5)
        doc = merged[0]
        assert doc.metadata["rrf_score"] == pytest.approx(1 / 61)
        assert doc.metadata["rrf_sources"] == ["dense"]
        assert doc.metadata["rrf_ranks"] == {"dense": 1}
        assert doc.metadata["rrf_chunk_hits"] == {"dense": 1}
        assert doc.metadata["final_score"] == doc.metadata["rrf_score"]

    def test_top_k_limits_results(self):
        dense = [make_doc(f"doc{i}", id=i) for i in range(1, 6)]
        merged = rrf_merge([("dense", dense)], top_k=2)
        assert len(merged) == 2

    def test_dedup_same_doc_within_source(self):
        """同一 source 内同一 id 多次命中只保留最佳 rank 算分一次"""
        dense = [make_doc("A", id=1), make_doc("A", id=1)]
        merged = rrf_merge([("dense", dense)], top_k=5)
        assert len(merged) == 1
        assert merged[0].metadata["rrf_score"] == pytest.approx(1 / 61)

    def test_empty_inputs(self):
        assert rrf_merge([], top_k=5) == []

    def test_content_hash_fallback_when_no_id(self):
        """无 PG id 时以 page_content hash 作为去重键"""
        dense = [make_doc("相同内容"), make_doc("相同内容")]
        merged = rrf_merge([("dense", dense)], top_k=5)
        assert len(merged) == 1


class TestDenseSearch:
    """稠密向量检索测试"""

    def _make_module(self, rows, **kwargs):
        pg = MagicMock()
        pg.get_cursor.return_value = make_cursor(rows)
        module = HybridRetrievalModule(pg=pg)
        return module, pg

    def test_dense_search_basic(self):
        rows = [
            {
                "id": 1,
                "text": "消防法规内容",
                "category": "regulation",
                "source_file": "f1",
                "source_name": "fire_regulation.pdf",
                "title": "第5.1.1条",
                "score": 0.92,
            }
        ]
        module, _ = self._make_module(rows)
        with patch(
            "graph_rag.vector_db.db_retriever.encode_query_dense",
            return_value=[0.1] * 1024,
        ):
            docs = module.dense_search("查询消防法规", top_k=5)
        assert len(docs) == 1
        doc = docs[0]
        assert doc.page_content == "消防法规内容"
        assert doc.metadata["search_type"] == "dense"
        assert doc.metadata["score"] == pytest.approx(0.92)
        assert doc.metadata["id"] == 1

    def test_dense_search_filters_below_threshold(self):
        rows = [{"id": 1, "text": "低分", "score": 0.05, "category": None, "source_file": "f", "title": "t"}]
        module, _ = self._make_module(rows)
        with patch(
            "graph_rag.vector_db.db_retriever.encode_query_dense",
            return_value=[0.1] * 1024,
        ):
            docs = module.dense_search("查询", score_threshold=0.1)
        assert docs == []

    def test_dense_search_category_filter(self):
        rows = [{"id": 1, "text": "内容", "score": 0.9, "category": "regulation", "source_file": "f", "title": "t"}]
        module, pg = self._make_module(rows)
        with patch(
            "graph_rag.vector_db.db_retriever.encode_query_dense",
            return_value=[0.1] * 1024,
        ):
            module.dense_search("查询", category="regulation")
        cur = pg.get_cursor.return_value
        sql, params = cur.execute.call_args.args
        assert "AND category = %s" in sql
        assert len(params) == 4  # vector, category, vector, top_k

    def test_dense_search_exception_returns_empty(self):
        pg = MagicMock()
        pg.get_cursor.side_effect = RuntimeError("db down")
        module = HybridRetrievalModule(pg=pg)
        with patch(
            "graph_rag.vector_db.db_retriever.encode_query_dense",
            return_value=[0.1] * 1024,
        ):
            docs = module.dense_search("查询")
        assert docs == []


class TestSparseSearch:
    """稀疏向量检索测试"""

    def test_sparse_search_basic(self):
        rows = [
            {
                "id": 2,
                "text": "条款内容",
                "category": "regulation",
                "source_file": "f2",
                "source_name": "std.pdf",
                "title": "5.1.1",
                "score": 0.85,
            }
        ]
        pg = MagicMock()
        pg.get_cursor.return_value = make_cursor(rows)
        module = HybridRetrievalModule(pg=pg)
        module._query_sparse_vector = MagicMock(return_value="<sparse_vec>")
        docs = module.sparse_search("5.1.1条", top_k=5)
        assert len(docs) == 1
        assert docs[0].metadata["search_type"] == "sparse"
        assert docs[0].metadata["score"] == pytest.approx(0.85)

    def test_sparse_search_threshold(self):
        rows = [{"id": 2, "text": "低分", "score": 0.02, "category": None, "source_file": "f", "title": "t"}]
        pg = MagicMock()
        pg.get_cursor.return_value = make_cursor(rows)
        module = HybridRetrievalModule(pg=pg)
        module._query_sparse_vector = MagicMock(return_value="<sparse_vec>")
        docs = module.sparse_search("查询", score_threshold=0.1)
        assert docs == []


class TestHybridSearch:
    """混合检索测试"""

    def test_hybrid_search_merges_both_routes(self):
        module = HybridRetrievalModule(pg=MagicMock())
        module.dense_search = MagicMock(
            return_value=[make_doc("语义结果", id=1, score=0.9, search_type="dense")]
        )
        module.sparse_search = MagicMock(
            return_value=[make_doc("关键词结果", id=2, score=0.8, search_type="sparse")]
        )
        docs = module.hybrid_search("查询", top_k=5)
        assert len(docs) == 2
        # 融合后 search_type 标记为 hybrid
        assert all(d.metadata["search_type"] == "hybrid" for d in docs)
        module.dense_search.assert_called_once()
        module.sparse_search.assert_called_once()

    def test_hybrid_search_expands_candidates(self):
        module = HybridRetrievalModule(pg=MagicMock())
        module.dense_search = MagicMock(return_value=[])
        module.sparse_search = MagicMock(return_value=[])
        module.hybrid_search("查询", top_k=3)
        # 两路检索各取 top_k * 2 扩大候选集
        module.dense_search.assert_called_once()
        assert module.dense_search.call_args.kwargs["top_k"] == 6


class TestLoadSourceChunks:
    """同源 chunk 懒加载测试"""

    def test_load_source_chunks(self):
        rows = [
            {"id": 1, "text": "c1", "category": "manual", "source_file": "hash1", "source_name": "m.pdf", "title": "t"},
            {"id": 2, "text": "c2", "category": "manual", "source_file": "hash1", "source_name": "m.pdf", "title": "t"},
        ]
        pg = MagicMock()
        pg.get_cursor.return_value = make_cursor(rows)
        module = HybridRetrievalModule(pg=pg)
        docs = module.load_source_chunks("hash1")
        assert len(docs) == 2
        assert docs[0].metadata["search_type"] == "parent_fill"
        pg.get_cursor.return_value.execute.assert_called_once()

    def test_load_source_chunks_exception_returns_empty(self):
        pg = MagicMock()
        pg.get_cursor.side_effect = RuntimeError("db down")
        module = HybridRetrievalModule(pg=pg)
        assert module.load_source_chunks("hash1") == []
