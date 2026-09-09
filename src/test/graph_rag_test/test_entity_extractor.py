"""
实体抽取模块单元测试（entity_extractor.py）

测试覆盖：
    1. EntityFusionService._is_simple_entity — 文本相似度判断
    2. EntityFusionService.fuse_entities — LLM + NER 结果融合
    3. LlmEntityExtractor._build_extract_prompt — Prompt 构建
    4. LlmEntityExtractor.extract — LLM 抽取（mock）
    5. DocumentGraphExtractionPipeline.extract — 并行编排（含超时路径）
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from graph_rag.entity_extractor import (
    DocumentGraphExtractionPipeline,
    Entity,
    EntityFusionService,
    ExtractResult,
    LlmEntityExtractor,
    Relation,
)


class TestIsSimpleEntity:
    """文本相似度判断测试"""

    def test_containment(self):
        assert EntityFusionService._is_simple_entity("烟感探测器", "烟感探测器-01") is True
        assert EntityFusionService._is_simple_entity("烟感探测器-01", "烟感探测器") is True

    def test_high_overlap(self):
        assert EntityFusionService._is_simple_entity("消火栓A", "消火栓B") is True

    def test_low_overlap(self):
        assert EntityFusionService._is_simple_entity("喷淋泵", "消防水箱") is False

    def test_empty_text(self):
        assert EntityFusionService._is_simple_entity("", "烟感") is False
        assert EntityFusionService._is_simple_entity("烟感", "") is False
        assert EntityFusionService._is_simple_entity("", "") is False

    def test_identical_text(self):
        assert EntityFusionService._is_simple_entity("喷淋头", "喷淋头") is True


class TestFuseEntities:
    """LLM + NER 结果融合测试"""

    def test_llm_none_uses_ner_only(self):
        service = EntityFusionService()
        ner_result = [{"text": "烟感探测器"}, {"text": "喷淋泵"}]
        result = service.fuse_entities(None, ner_result)
        assert len(result.entities) == 2
        assert all(e.type == "Unknown" for e in result.entities)
        assert result.relations == []

    def test_ner_supplements_llm(self):
        service = EntityFusionService()
        llm_result = ExtractResult(
            entities=[Entity(name="烟感探测器", type="Equipment")],
            relations=[Relation(source="烟感探测器", target="ICU病房", relation="安装于")],
        )
        ner_result = [{"text": "喷淋泵"}]
        result = service.fuse_entities(llm_result, ner_result)
        names = [e.name for e in result.entities]
        assert "烟感探测器" in names
        assert "喷淋泵" in names
        # relations 保留 LLM 结果
        assert len(result.relations) == 1

    def test_ner_overlap_not_duplicated(self):
        service = EntityFusionService()
        llm_result = ExtractResult(entities=[Entity(name="烟感探测器", type="Equipment")], relations=[])
        ner_result = [{"text": "烟感探测器-01"}]  # 与 LLM 实体包含关系
        result = service.fuse_entities(llm_result, ner_result)
        assert len(result.entities) == 1

    def test_empty_ner(self):
        service = EntityFusionService()
        llm_result = ExtractResult(entities=[Entity(name="烟感探测器", type="Equipment")], relations=[])
        result = service.fuse_entities(llm_result, [])
        assert len(result.entities) == 1


class TestLlmEntityExtractor:
    """LLM 实体抽取器测试"""

    def test_build_extract_prompt_contains_query_and_schema(self):
        extractor = LlmEntityExtractor(llm=MagicMock())
        prompt = extractor._build_extract_prompt("查询B栋3层烟感设备状态")
        assert "查询B栋3层烟感设备状态" in prompt
        assert "Equipment" in prompt  # 节点类型
        assert "安装于" in prompt  # 关系类型
        assert "JSON" in prompt

    def test_build_extract_prompt_with_context(self):
        extractor = LlmEntityExtractor(llm=MagicMock())
        prompt = extractor._build_extract_prompt("查询设备", context="用户位于B栋3层")
        assert "用户位于B栋3层" in prompt

    @pytest.mark.asyncio
    async def test_extract_structured_output(self):
        llm = MagicMock()
        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(
            return_value=ExtractResult(entities=[Entity(name="烟感探测器", type="Equipment")], relations=[])
        )
        llm.with_structured_output = MagicMock(return_value=structured_llm)
        extractor = LlmEntityExtractor(llm=llm)
        result = await extractor.extract("查询烟感探测器状态")
        assert result is not None
        assert result.entities[0].name == "烟感探测器"

    @pytest.mark.asyncio
    async def test_extract_falls_back_to_general_output(self):
        llm = MagicMock()
        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(return_value="not an ExtractResult")
        llm.with_structured_output = MagicMock(return_value=structured_llm)
        llm.ainvoke = AsyncMock(
            return_value=ExtractResult(entities=[Entity(name="喷淋泵", type="Equipment")], relations=[])
        )
        extractor = LlmEntityExtractor(llm=llm)
        result = await extractor.extract("查询喷淋泵")
        assert result is not None
        assert result.entities[0].name == "喷淋泵"

    @pytest.mark.asyncio
    async def test_extract_exception_returns_none(self):
        llm = MagicMock()
        structured_llm = MagicMock()
        structured_llm.ainvoke = AsyncMock(side_effect=RuntimeError("model error"))
        llm.with_structured_output = MagicMock(return_value=structured_llm)
        extractor = LlmEntityExtractor(llm=llm)
        result = await extractor.extract("查询")
        assert result is None


@pytest.mark.asyncio
class TestDocumentGraphExtractionPipeline:
    """并行抽取编排测试"""

    async def test_extract_normal_path(self):
        llm_entity = MagicMock()
        llm_entity.extract = AsyncMock(
            return_value=ExtractResult(entities=[Entity(name="烟感探测器", type="Equipment")], relations=[])
        )
        ner_entity = MagicMock()
        ner_entity.extract = AsyncMock(return_value=[{"text": "喷淋泵"}])
        fusion_service = EntityFusionService()
        pipeline = DocumentGraphExtractionPipeline(llm_entity, ner_entity, fusion_service)

        result = await pipeline.extract("查询烟感探测器")
        names = [e.name for e in result.entities]
        assert "烟感探测器" in names
        assert "喷淋泵" in names

    async def test_extract_llm_timeout_path(self):
        llm_entity = MagicMock()
        llm_entity.extract = AsyncMock(return_value=None)
        ner_entity = MagicMock()
        ner_entity.extract = AsyncMock(return_value=[{"text": "烟感探测器"}])
        fusion_service = EntityFusionService()
        pipeline = DocumentGraphExtractionPipeline(llm_entity, ner_entity, fusion_service)

        with patch(
            "graph_rag.entity_extractor.asyncio.wait_for",
            AsyncMock(side_effect=asyncio.TimeoutError()),
        ):
            result = await pipeline.extract("查询烟感探测器")
        # LLM 超时后仍返回 NER 结果
        assert len(result.entities) == 1
        assert result.entities[0].name == "烟感探测器"

    async def test_extract_with_context(self):
        llm_entity = MagicMock()
        llm_entity.extract = AsyncMock(
            return_value=ExtractResult(entities=[Entity(name="ICU病房", type="Zone")], relations=[])
        )
        ner_entity = MagicMock()
        ner_entity.extract = AsyncMock(return_value=[])
        fusion_service = EntityFusionService()
        pipeline = DocumentGraphExtractionPipeline(llm_entity, ner_entity, fusion_service)

        result = await pipeline.extract("ICU病房有哪些设备", context="用户位于医院")
        llm_entity.extract.assert_awaited_with("ICU病房有哪些设备", "用户位于医院")
        assert result.entities[0].name == "ICU病房"
