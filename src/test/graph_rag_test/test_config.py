"""
GraphRAG 配置模块单元测试（config.py）

测试覆盖：
    1. GraphRAGSettings 默认值（不受 .env / 环境变量影响）
    2. get_settings() 单例行为
"""

import pytest

from graph_rag.config import GraphRAGSettings, get_settings

# GraphRAGSettings 全部字段名（大写后即环境变量名）
_SETTINGS_FIELDS = [
    "pg_host", "pg_port", "pg_user", "pg_password", "pg_dbname",
    "neo4j_uri", "neo4j_user", "neo4j_password", "neo4j_database",
    "embedding_model_name", "embedding_device",
    "default_top_k", "default_graph_depth", "min_similarity", "llm_timeout",
    "ragas_threshold",
    "java_api_base_url", "mcp_host", "mcp_port", "mcp_path",
]


@pytest.fixture
def clean_settings(monkeypatch):
    """构造一个不受 .env 与进程环境变量影响的 GraphRAGSettings 实例"""
    for field in _SETTINGS_FIELDS:
        monkeypatch.delenv(field.upper(), raising=False)
    return GraphRAGSettings(_env_file=None)


class TestGraphRAGSettingsDefaults:
    """GraphRAGSettings 默认配置项测试"""

    def test_default_pg_config(self, clean_settings):
        assert clean_settings.pg_host == "localhost"
        assert clean_settings.pg_port == 5432
        assert clean_settings.pg_user == "postgres"
        assert clean_settings.pg_dbname == "fire_rag"

    def test_default_neo4j_config(self, clean_settings):
        assert clean_settings.neo4j_uri == "bolt://localhost:7687"
        assert clean_settings.neo4j_user == "neo4j"
        assert clean_settings.neo4j_password == "neo4j"
        assert clean_settings.neo4j_database == "neo4j"

    def test_default_embedding_config(self, clean_settings):
        assert clean_settings.embedding_model_name == "BAAI/bge-m3"
        assert clean_settings.embedding_device == "cpu"

    def test_default_retrieval_config(self, clean_settings):
        assert clean_settings.default_top_k == 5
        assert clean_settings.default_graph_depth == 2
        assert clean_settings.min_similarity == 0.3
        assert clean_settings.llm_timeout == 2.0

    def test_default_evaluation_config(self, clean_settings):
        assert clean_settings.ragas_threshold == 0.7

    def test_extra_env_ignored(self, monkeypatch):
        """未在模型中声明的环境变量应被忽略（extra='ignore'）"""
        monkeypatch.delenv("UNKNOWN_KEY", raising=False)
        settings = GraphRAGSettings(_env_file=None, _extra_env={"UNKNOWN_KEY": "x"})
        assert not hasattr(settings, "UNKNOWN_KEY")


class TestGetSettings:
    """get_settings() 单例行为测试"""

    def test_returns_settings_instance(self):
        assert isinstance(get_settings(), GraphRAGSettings)

    def test_singleton_identity(self):
        """多次调用应返回同一实例（线程安全懒加载单例）"""
        assert get_settings() is get_settings()
