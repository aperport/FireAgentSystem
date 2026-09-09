"""
GraphRAG 查询编排器单元测试（orchestrator.py）

测试覆盖：
    1. rag_search() 正常链路：实体抽取 → 并行检索 → 融合 → 持久化
    2. 实体抽取为 None 时图遍历返回空
    3. 检索模块单例访问
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.documents import Document

from graph_rag.entity_extractor import Entity, ExtractResult
from graph_rag.orchestrator import GraphRAGOrchestrator

pytestmark = pytest.mark.asyncio

_EMPTY = object()  # 哨兵：区分"未传参"与"显式传 None"


def make_doc(content: str, **metadata) -> Document:
    return Document(page_content=content, metadata=metadata)


def make_extract_result() -> ExtractResult:
    return ExtractResult(
        entities=[Entity(name="值班", type="Module")],
        relations=[],
    )


def make_orchestrator(
    extract_return=_EMPTY,
    graph_return=_EMPTY,
    vector_return=_EMPTY,
    fused_return=_EMPTY,
):
    extract_value = make_extract_result() if extract_return is _EMPTY else extract_return
    graph_value = [] if graph_return is _EMPTY else graph_return
    vector_value = [] if vector_return is _EMPTY else vector_return
    fused_value = [] if fused_return is _EMPTY else fused_return

    graph_traverser = MagicMock()
    graph_traverser.traverse = AsyncMock(return_value=graph_value)

    doc_extraction = MagicMock()
    doc_extraction.extract = AsyncMock(return_value=extract_value)

    context_fusion = MagicMock()
    context_fusion.fuse = AsyncMock(return_value=fused_value)

    vector_retriever = MagicMock()
    vector_retriever.search = AsyncMock(return_value=vector_value)

    orchestrator = GraphRAGOrchestrator(
        graph_traverser=graph_traverser,
        doc_extraction=doc_extraction,
        context_fusion=context_fusion,
        vector_retriever=vector_retriever,
    )
    return orchestrator, graph_traverser, doc_extraction, context_fusion, vector_retriever


class TestGraphRAGOrchestrator:
    """编排器测试"""

    @patch("graph_rag.orchestrator.append_json_item", new_callable=AsyncMock)
    @patch("graph_rag.orchestrator.get_retrieval_module")
    async def test_rag_search_full_pipeline(self, mock_get_retrieval, mock_append):
        mock_get_retrieval.return_value = MagicMock()

        fused = [make_doc("融合后的上下文", score=0.9)]
        orch, _, doc_extraction, context_fusion, vector_retriever = make_orchestrator(
            graph_return=[{"module": {"name": "值班"}}],
            fused_return=fused,
        )
        result = await orch.rag_search("值班如何交接")
        assert result == fused
        doc_extraction.extract.assert_awaited_once_with("值班如何交接")
        vector_retriever.search.assert_awaited_once()
        context_fusion.fuse.assert_awaited_once()
        mock_append.assert_awaited_once()

    @patch("graph_rag.orchestrator.append_json_item", new_callable=AsyncMock)
    @patch("graph_rag.orchestrator.get_retrieval_module")
    async def test_rag_search_none_entity_result(self, mock_get_retrieval, mock_append):
        mock_get_retrieval.return_value = MagicMock()

        orch, graph_traverser, _, _, _ = make_orchestrator(extract_return=None)
        await orch.rag_search("查询")
        # entity_result 为 None 时图遍历返回空
        graph_traverser.traverse.assert_not_awaited()
        mock_append.assert_awaited_once()

    @patch("graph_rag.orchestrator.get_retrieval_module")
    async def test_orchestrator_retrieval_module_injected(self, mock_get_retrieval):
        """构造时通过 get_retrieval_module() 获取检索模块单例"""
        fake_module = MagicMock()
        mock_get_retrieval.return_value = fake_module
        orch, *_ = make_orchestrator()
        assert orch.retrieval_module is fake_module
