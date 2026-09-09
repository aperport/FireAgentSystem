"""
上下文融合模块单元测试（context_fusion.py）

测试覆盖：
    1. graph_records_to_documents — 图记录 → Document 转换
    2. deduplicate — 实体去重
    3. sort_by_relevance — 相关性排序
    4. attach_parent_documents — 父文档/相邻 chunk 回填
    5. truncate_to_budget — Token 预算截断
    6. fuse — 异步融合管线
"""

import pytest
from langchain_core.documents import Document

from graph_rag.context_fusion import ContextFusionModule


def make_doc(content: str, **metadata) -> Document:
    return Document(page_content=content, metadata=metadata)


class TestGraphRecordsToDocuments:
    """图记录 → Document 转换测试"""

    def test_empty_records(self):
        assert ContextFusionModule.graph_records_to_documents(None) == []
        assert ContextFusionModule.graph_records_to_documents([]) == []

    def test_single_record_multiple_nodes(self):
        records = [
            {
                "module": {"name": "值班", "description": "值班管理"},
                "function": {"name": "交接班"},
                "step": None,
            }
        ]
        docs = ContextFusionModule.graph_records_to_documents(records)
        assert len(docs) == 2
        # Module 节点
        module_doc = docs[0]
        assert module_doc.metadata["node_label"] == "Module"
        assert module_doc.metadata["node_name"] == "值班"
        assert module_doc.metadata["hop_count"] == 1
        assert module_doc.metadata["search_type"] == "graph"
        assert "name: 值班" in module_doc.page_content
        # Function 节点
        assert docs[1].metadata["node_label"] == "Function"

    def test_none_nodes_skipped(self):
        records = [{"module": None, "function": {"name": "交接班"}}]
        docs = ContextFusionModule.graph_records_to_documents(records)
        assert len(docs) == 1
        assert docs[0].metadata["node_label"] == "Function"

    def test_hop_count_passed_to_metadata(self):
        records = [{"module": {"name": "巡检"}}]
        docs = ContextFusionModule.graph_records_to_documents(records, hop_count=3)
        assert docs[0].metadata["hop_count"] == 3

    def test_same_record_dedup(self):
        """同一 record 内相同 label+name 只保留一次（equipment/dependent_equipment）"""
        records = [{"equipment": {"name": "消火栓-01"}, "dependent_equipment": {"name": "消火栓-01"}}]
        docs = ContextFusionModule.graph_records_to_documents(records)
        assert len(docs) == 1

    def test_unknown_variable_uses_var_name_as_label(self):
        records = [{"custom_node": {"name": "x"}}]
        docs = ContextFusionModule.graph_records_to_documents(records)
        assert docs[0].metadata["node_label"] == "custom_node"


class TestDeduplicate:
    """实体去重测试"""

    def test_empty(self):
        assert ContextFusionModule.deduplicate([]) == []

    def test_dedup_by_pg_id(self):
        docs = [
            make_doc("内容A", id=1, search_type="dense"),
            make_doc("内容A", id=1, search_type="sparse"),
        ]
        result = ContextFusionModule.deduplicate(docs)
        assert len(result) == 1
        assert result[0].metadata["dedup_sources"] == ["dense", "sparse"]

    def test_dedup_by_content_hash(self):
        docs = [
            make_doc("相同内容", search_type="dense"),
            make_doc("相同内容", search_type="sparse"),
        ]
        result = ContextFusionModule.deduplicate(docs)
        assert len(result) == 1

    def test_distinct_docs_kept(self):
        docs = [make_doc("内容A", id=1), make_doc("内容B", id=2)]
        result = ContextFusionModule.deduplicate(docs)
        assert len(result) == 2

    def test_richer_metadata_version_kept(self):
        docs = [
            make_doc("内容A", id=1, score=0.8),
            make_doc("内容A", id=1),
        ]
        result = ContextFusionModule.deduplicate(docs)
        assert len(result) == 1
        assert result[0].metadata.get("score") == 0.8

    def test_single_source_no_dedup_sources_marker(self):
        docs = [make_doc("内容A", id=1, search_type="dense")]
        result = ContextFusionModule.deduplicate(docs)
        assert "dedup_sources" not in result[0].metadata


class TestSortByRelevance:
    """相关性排序测试"""

    def test_empty(self):
        assert ContextFusionModule.sort_by_relevance([]) == []

    def test_rrf_score_priority(self):
        docs = [
            make_doc("低rrf", rrf_score=0.1, score=0.9),
            make_doc("高rrf", rrf_score=0.9, score=0.1),
        ]
        result = ContextFusionModule.sort_by_relevance(docs)
        assert result[0].page_content == "高rrf"

    def test_score_fallback(self):
        docs = [
            make_doc("低分", score=0.2),
            make_doc("高分", score=0.9),
        ]
        result = ContextFusionModule.sort_by_relevance(docs)
        assert result[0].page_content == "高分"

    def test_hop_weight(self):
        """hop_weight = 1/(hop_count+1)，1 跳(0.5) > 2 跳(0.33)"""
        docs = [
            make_doc("两跳", hop_count=2),
            make_doc("一跳", hop_count=1),
        ]
        result = ContextFusionModule.sort_by_relevance(docs)
        assert result[0].page_content == "一跳"

    def test_no_score_sorted_last(self):
        docs = [
            make_doc("无分数"),
            make_doc("有分数", score=0.5),
        ]
        result = ContextFusionModule.sort_by_relevance(docs)
        assert result[0].page_content == "有分数"
        assert result[1].page_content == "无分数"


class TestAttachParentDocuments:
    """相邻 chunk 回填测试"""

    def test_empty_chunks(self):
        module = ContextFusionModule()
        assert module.attach_parent_documents([]) == []

    def test_backfill_with_loader(self):
        sibling_docs = [
            make_doc("chunk1", id=1, source_file="f.pdf"),
            make_doc("chunk2", id=2, source_file="f.pdf"),
            make_doc("chunk3", id=3, source_file="f.pdf"),
        ]
        module = ContextFusionModule(loader=lambda f: sibling_docs)
        chunks = [make_doc("chunk2", id=2, source_file="f.pdf")]
        result = module.attach_parent_documents(chunks)
        # 原始 chunk + 前后各 1 个 = 3
        assert len(result) == 3
        filled = [d for d in result if d.metadata.get("context_fill")]
        assert len(filled) == 2

    def test_top_n_limits_backfill(self):
        sibling_docs = [
            make_doc(f"chunk{i}", id=i, source_file="f.pdf") for i in range(1, 6)
        ]
        module = ContextFusionModule(loader=lambda f: sibling_docs)
        chunks = [
            make_doc("chunk1", id=1, source_file="f.pdf"),
            make_doc("chunk5", id=5, source_file="f.pdf"),
        ]
        result = module.attach_parent_documents(chunks, top_n=1)
        # 只回填第一个命中 chunk（chunk1）的邻居
        filled = [d for d in result if d.metadata.get("context_fill")]
        assert all(d.metadata.get("source_hit_id") == 1 for d in filled)

    def test_context_window(self):
        sibling_docs = [
            make_doc(f"chunk{i}", id=i, source_file="f.pdf") for i in range(1, 8)
        ]
        module = ContextFusionModule(loader=lambda f: sibling_docs)
        chunks = [make_doc("chunk4", id=4, source_file="f.pdf")]
        result = module.attach_parent_documents(chunks, context_window=2)
        filled = [d for d in result if d.metadata.get("context_fill")]
        # 前后各 2 个 = 4
        assert len(filled) == 4

    def test_loader_caching(self):
        calls = []
        sibling_docs = [make_doc("chunk1", id=1, source_file="f.pdf")]

        def loader(f):
            calls.append(f)
            return sibling_docs

        module = ContextFusionModule(loader=loader)
        chunks = [make_doc("chunk1", id=1, source_file="f.pdf")]
        module.attach_parent_documents(chunks)
        module.attach_parent_documents(chunks)
        # 第二次命中缓存，不重复调用 loader
        assert len(calls) == 1

    def test_no_source_file_skipped(self):
        module = ContextFusionModule(loader=lambda f: [])
        chunks = [make_doc("chunk1", id=1)]
        result = module.attach_parent_documents(chunks)
        assert len(result) == 1


class TestTruncateToBudget:
    """Token 预算截断测试"""

    def test_zero_budget_returns_empty(self):
        docs = [make_doc("内容")]
        assert ContextFusionModule.truncate_to_budget(docs, 0) == []
        assert ContextFusionModule.truncate_to_budget([], 100) == []

    def test_all_docs_fit(self):
        docs = [make_doc("短内容"), make_doc("另一条")]
        result = ContextFusionModule.truncate_to_budget(docs, 10000)
        assert len(result) == 2

    def test_truncates_last_doc(self):
        docs = [
            make_doc("短"),  # 1 token，完整放下
            make_doc("第二段内容很长" * 100),  # 放不下，截断
        ]
        result = ContextFusionModule.truncate_to_budget(docs, 5)
        assert len(result) == 2
        assert result[-1].metadata.get("truncated") is True
        assert result[-1].page_content.endswith("...[截断]")

    def test_small_budget_keeps_first_doc_only(self):
        docs = [
            make_doc("A" * 200, id=1),
            make_doc("B" * 200, id=2),
        ]
        result = ContextFusionModule.truncate_to_budget(docs, 10)
        assert len(result) == 1
        assert result[0].metadata["id"] == 1


class TestEstimateTokens:
    """Token 粗略估算测试"""

    def test_chinese_token_estimation(self):
        # 中文约 1.5 字/token：4 字 → int(4/1.5) = 2
        assert ContextFusionModule._estimate_tokens("消防设备") == 2

    def test_english_token_estimation(self):
        # 英文约 4 字符/token：8 字符 ≈ 2 token
        assert ContextFusionModule._estimate_tokens("firefoam") == 2

    def test_empty_text(self):
        assert ContextFusionModule._estimate_tokens("") == 0


@pytest.mark.asyncio
class TestFuse:
    """异步融合管线测试"""

    async def test_fuse_empty_input(self):
        module = ContextFusionModule()
        result = await module.fuse(vector_docs=[], graph_records=None)
        assert result == []

    async def test_fuse_full_pipeline(self):
        module = ContextFusionModule()
        vector_docs = [make_doc("向量内容", id=1, score=0.9)]
        graph_records = [{"module": {"name": "值班"}}]
        result = await module.fuse(vector_docs=vector_docs, graph_records=graph_records, token_budget=0)
        assert len(result) == 2
        # 图文档带有 graph metadata
        graph_docs = [d for d in result if d.metadata.get("search_type") == "graph"]
        assert len(graph_docs) == 1
        assert graph_docs[0].metadata["node_name"] == "值班"

    async def test_fuse_dedups_duplicate(self):
        module = ContextFusionModule()
        # 两路完全相同的 chunk（无 PG id）→ 经内容 hash 去重为 1 份
        vector_docs = [
            make_doc("相同内容", score=0.9, search_type="dense"),
            make_doc("相同内容", score=0.8, search_type="sparse"),
        ]
        result = await module.fuse(vector_docs=vector_docs, graph_records=None)
        assert len(result) == 1

    async def test_fuse_with_token_budget(self):
        module = ContextFusionModule()
        vector_docs = [make_doc("内容" * 500, id=1, score=0.9)]
        result = await module.fuse(vector_docs=vector_docs, graph_records=[], token_budget=10)
        assert len(result) == 1
        assert result[0].metadata.get("truncated") is True
