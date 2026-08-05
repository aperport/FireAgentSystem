"""
GraphRAG 配置模块 — 集中管理所有配置项，一处定义全局读取。

使用 pydantic-settings BaseSettings，自动从 .env 读取环境变量。
各模块统一通过 get_settings() 获取配置，不再各自 os.getenv()。

用法：
    from graph_rag.config import get_settings
    s = get_settings()
    print(s.pg_host, s.neo4j_uri, s.embedding_model_name)
"""

import threading
from pydantic_settings import BaseSettings


class GraphRAGSettings(BaseSettings):
    """GraphRAG 全局配置，从 .env 自动读取，带合理默认值。"""

    # ── PostgreSQL + pgvector ──
    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_user: str = "postgres"
    pg_password: str = ""
    pg_dbname: str = "fire_rag"

    # ── Neo4j ──
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "neo4j"
    neo4j_database: str = "neo4j"

    # ── Embedding ──
    embedding_model_name: str = "BAAI/bge-small-zh-v1.5"
    embedding_device: str = "cpu"

    # ── 检索参数 ──
    default_top_k: int = 5
    default_graph_depth: int = 2
    min_similarity: float = 0.3
    llm_timeout: float = 2.0

    # ── 评估 ──
    ragas_threshold: float = 0.7

    # ── MCP Server ──
    java_api_base_url: str = "http://127.0.0.1:8080"
    mcp_host: str = "127.0.0.1"
    mcp_port: int = 8000
    mcp_path: str = "/mcp"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


_instance: GraphRAGSettings | None = None
_lock = threading.Lock()


def get_settings() -> GraphRAGSettings:
    """获取全局配置单例（线程安全，懒加载）。"""
    global _instance
    if _instance is None:
        with _lock:
            if _instance is not None:
                return _instance
            _instance = GraphRAGSettings()
    return _instance
