"""
规则辅助抽取模块单元测试（rule_extractors.py）

测试覆盖：
    1. extract_clause_numbers() 各正则模式
    2. 条款号去重
    3. 无条款文本返回空列表
"""

import pytest

from graph_rag.entity_extractor import Entity
from graph_rag.rule_extractors import extract_clause_numbers


class TestExtractClauseNumbers:
    """条款号正则提取测试"""

    def test_empty_text_returns_empty(self):
        assert extract_clause_numbers("") == []
        assert extract_clause_numbers("这里没有任何条款") == []

    def test_chinese_numeral_clause_with_item(self):
        """第X条第X款（中文数字）"""
        result = extract_clause_numbers("见第一条第一款之规定")
        names = [e.name for e in result]
        assert "第一条第一款" in names
        assert all(e.type == "Clause" for e in result)

    def test_arabic_clause_with_item(self):
        """第X条第X款（阿拉伯数字）"""
        result = extract_clause_numbers("参见第1条第2款")
        names = [e.name for e in result]
        assert "第1条第2款" in names

    def test_dotted_clause(self):
        """X.X.X节 / X.X.X条（阿拉伯数字点号）"""
        result = extract_clause_numbers("详见 5.1.1节 与 5.1.1条")
        names = [e.name for e in result]
        assert "5.1.1节" in names
        assert "5.1.1条" in names

    def test_dotted_two_level_clause(self):
        """X.X节（两位版本）"""
        result = extract_clause_numbers("本规范 5.1节 有说明")
        names = [e.name for e in result]
        assert "5.1节" in names

    def test_chinese_numeral_clause(self):
        """第X条（中文数字）"""
        result = extract_clause_numbers("第一百二十三条")
        names = [e.name for e in result]
        assert "第一百二十三条" in names

    def test_arabic_clause(self):
        """第X条（阿拉伯数字）"""
        result = extract_clause_numbers("第7条规定")
        names = [e.name for e in result]
        assert "第7条" in names

    def test_deduplication(self):
        """重复条款号只保留一个 Entity"""
        result = extract_clause_numbers("第1条、第1条、第2条")
        names = [e.name for e in result]
        assert names == ["第1条", "第2条"]

    def test_mixed_text_extracts_all(self):
        text = "依据《规范》第一条、5.1.1节，执行第3条第2款所述要求"
        result = extract_clause_numbers(text)
        names = [e.name for e in result]
        for expected in ["第一条", "5.1.1节", "第3条第2款"]:
            assert expected in names

    def test_returns_entity_objects(self):
        result = extract_clause_numbers("第5条")
        assert len(result) == 1
        entity = result[0]
        assert isinstance(entity, Entity)
        assert entity.name == "第5条"
        assert entity.type == "Clause"
