"""
向量检索统一入口单元测试（vector_retriever.py）

测试覆盖：
    1. search() 按 search_type 分发到 dense / sparse / hybrid
    2. 未知检索类型回退到 hybrid
    3. token_budget 截断调用
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.documents import Document

from graph_rag.vector_retriever import VectorRetriever

pytestmark = pytest.mark.asyncio


def make_doc(content: str, **metadata) -> Document:
    return Document(page_content=content, metadata=metadata)


def make_retriever(docs: list[Document] | None = None) -> tuple[VectorRetriever, MagicMock]:
    docs = docs if docs is not None else []
    retrieval_module = MagicMock()
    retrieval_module.dense_search = MagicMock(return_value=docs)
    retrieval_module.sparse_search = MagicMock(return_value=docs)
    retrieval_module.hybrid_search = MagicMock(return_value=docs)
    retriever = VectorRetriever(retrieval_module=retrieval_module)
    return retriever, retrieval_module


class TestSearchDispatch:
    """检索策略分发测试"""

    async def test_dense_dispatch(self):
        docs = [make_doc("语义结果", id=1)]
        retriever, module = make_retriever(docs)
        result = await retriever.search("查询", search_type="dense", top_k=5)
        module.dense_search.assert_called_once()
        module.sparse_search.assert_not_called()
        assert result == docs

    async def test_sparse_dispatch(self):
        retriever, module = make_retriever()
        await retriever.search("查询", search_type="sparse")
        module.sparse_search.assert_called_once()
        module.dense_search.assert_not_called()

    async def test_hybrid_dispatch(self):
        retriever, module = make_retriever()
        await retriever.search("查询", search_type="hybrid")
        module.hybrid_search.assert_called_once()

    async def test_unknown_type_falls_back_to_hybrid(self):
        retriever, module = make_retriever()
        await retriever.search("查询", search_type="bm25_legacy")
        module.hybrid_search.assert_called_once()

    async def test_dense_passes_params(self):
        retriever, module = make_retriever()
        await retriever.search("查询", search_type="dense", top_k=8, category="regulation", score_threshold=0.3)
        module.dense_search.assert_called_once_with(
            "查询",
            top_k=8,
            category="regulation",
            score_threshold=0.3,
        )


class TestTokenBudget:
    """Token 预算截断测试"""

    async def test_token_budget_triggers_truncation(self):
        retriever, module = make_retriever()
        # 替换 fusion 为 spy，验证截断被调用
        retriever.fusion_module = MagicMock()
        await retriever.search("查询", search_type="dense", token_budget=100)
        retriever.fusion_module.truncate_to_budget.assert_called_once()

    async def test_no_token_budget_skips_truncation(self):
        retriever, module = make_retriever()
        retriever.fusion_module = MagicMock()
        await retriever.search("查询", search_type="dense", token_budget=0)
        retriever.fusion_module.truncate_to_budget.assert_not_called()
