"""
消防后勤智能助手 — 路径常量 / Store / Checkpoint / 子Agent配置。

路径常量：
    LOCAL_SKILLS_DIR   — 本地skills目录（沙箱同步用，管理助手自定义分析场景）
    SANDBOX_SKILLS_ROOT — 沙箱中的skills根路径
    LOCAL_AGENTS_MD    — Agent行为准则文件路径（消防后勤AGENTS.md）

Store配置：
    STORE = InMemoryStore()  — 用户偏好存储，重启丢失，后续应迁至持久化Store

Checkpoint配置：
    MongoDBSavers — Agent对话状态持久化，支持Human-in-the-Loop和跨重启恢复

子Agent名称映射：
    SCOPE_MAP = {"main": "main", "fire-qa-assistant": "qa", "fire-management-analyst": "management"}

模型配置：
    SUMMARY_MODEL = DeepSeek_LLM  — 摘要/实体抽取用模型
"""
from pathlib import Path
from agent.llm_config import DeepSeek_LLM
from langchain.chat_models import BaseChatModel
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.mongodb import MongoDBSaver
from pymongo import MongoClient

LOCAL_SKILLS_DIR = "skills"
# 沙箱skills文件夹路径
SANDBOX_SKILLS_ROOT = "/opt/skills"

# ---------- 路径常量 ----------
EXAMPLE_DIR = Path(__file__).parent.parent


# 本地的Agent记忆文件
LOCAL_AGENTS_MD = EXAMPLE_DIR / "agent/memory/AGENTS.md"

# 子 Agent 名称 → 技能 scope 目录映射
SCOPE_MAP = {
    "main": "main",
    "fire-qa-assistant": "qa",
    "fire-management-analyst": "management",
}

# 摘要模型
SUMMARY_MODEL: BaseChatModel = DeepSeek_LLM

# 记忆存储，此处存到了内存，实际应该持久化
STORE = InMemoryStore()


# ---------- MongoDB 配置（用于持久化 Agent 短期记忆/checkpoint） ----------
MONGODB_URI = "mongodb://root:123456@39.100.100.28:27017/?authSource=admin"
MONGODB_DB_NAME = "langchain_db"
MONGODB_CHECKPOINT_COLLECTION = "checkpoints"


# MongoDBSaver: Agent 对话状态的 MongoDB 持久化 checkpointer。
# 支持 Human-in-the-Loop（interrupt 状态持久化）和跨重启对话恢复。
_mongodb_client = MongoClient(MONGODB_URI)
# 检查点
CHECKPOINT = MongoDBSaver(
    client=_mongodb_client,
    db_name=MONGODB_DB_NAME,
    checkpoint_collection_name=MONGODB_CHECKPOINT_COLLECTION,
)

# 技能 StoreBackend 命名空间（按 Agent scope 组织，无用户隔离）
SKILLS_STORE_NAMESPACE = ("skills",)


