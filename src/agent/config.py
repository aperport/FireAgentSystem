"""
消防后勤智能助手 — 路径常量 / Store / Checkpoint / 子Agent配置。

路径常量：
    LOCAL_SKILLS_DIR   — 本地skills目录（沙箱同步用，管理助手自定义分析场景）
    SANDBOX_SKILLS_ROOT — 沙箱中的skills根路径
    LOCAL_AGENTS_MD    — Agent行为准则文件路径（消防后勤AGENTS.md）

Store配置：
    STORE = InMemoryStore()  — 用户偏好存储，重启丢失，后续应迁至持久化Store

Checkpoint配置：
    PostgresSaver — Agent对话状态持久化，支持Human-in-the-Loop和跨重启恢复

子Agent名称映射：
    SCOPE_MAP = {"main": "main", "fire-qa-assistant": "qa", "fire-management-analyst": "management"}

模型配置：
    SUMMARY_MODEL = DeepSeek_LLM  — 摘要/实体抽取用模型
"""
from pathlib import Path

from agent.llm_config import DeepSeek_LLM
from langchain_core.language_models import BaseChatModel
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore

from graph_rag.config import get_settings

LOCAL_SKILLS_DIR = "skills"
SANDBOX_SKILLS_ROOT = "/opt/skills"

EXAMPLE_DIR = Path(__file__).parent.parent

LOCAL_AGENTS_MD = EXAMPLE_DIR / "agent/memory/AGENTS.md"

SCOPE_MAP = {
    "main": "main",
    "fire-qa-assistant": "qa",
    "fire-management-analyst": "management",
}

SUMMARY_MODEL: BaseChatModel = DeepSeek_LLM

STORE = InMemoryStore()

# ── Store Checkpoint（懒加载，避免 import 时连接数据库）──
_STORE: PostgresStore 

def get_store() -> PostgresStore:
    """获取 Store 单例（懒加载）
    """
    global _STORE
    if _STORE is None:
        s = get_settings()
        conn_str = f"postgresql://{s.pg_user}:{s.pg_password}@{s.pg_host}:{s.pg_port}/{s.pg_dbname}"
        _STORE = PostgresStore.from_conn_string(conn_str)
        _STORE.setup()
    return _STORE

class _StoreProxy:
    """代理对象，延迟连接数据库，行为与 PostgresSaver 一致。"""
    def __getattr__(self, name):
        return getattr(get_store(), name)
STORE = _StoreProxy()


# ── PostgreSQL Checkpoint（懒加载，避免 import 时连接数据库）──

_CHECKPOINT: PostgresSaver


def get_checkpointer() -> PostgresSaver:
    """获取 Checkpoint 单例（懒加载）。"""
    global _CHECKPOINT
    if _CHECKPOINT is None:
        s = get_settings()
        conn_str = f"postgresql://{s.pg_user}:{s.pg_password}@{s.pg_host}:{s.pg_port}/{s.pg_dbname}"
        _CHECKPOINT = PostgresSaver.from_conn_string(conn_str)
        _CHECKPOINT.setup()
    return _CHECKPOINT


# ponytail: 兼容旧代码中 `from agent.config import CHECKPOINT` 的引用
# 懒加载代理，首次访问时才连接数据库
class _CheckpointProxy:
    """代理对象，延迟连接数据库，行为与 PostgresSaver 一致。"""
    def __getattr__(self, name):
        return getattr(get_checkpointer(), name)


CHECKPOINT = _CheckpointProxy()

SKILLS_STORE_NAMESPACE = ("skills",)
