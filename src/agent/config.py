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
import os
from pathlib import Path
from dotenv import load_dotenv

from agent.llm_config import DeepSeek_LLM
from langchain_core.language_models import BaseChatModel
from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.postgres import PostgresSaver
import psycopg

# 加载 .env 环境变量
load_dotenv()

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





# 记忆存储，存储类型有两种：内存（InMemory）和持久化（PostgreSQL，manggodb） 其他不支持的数据库可以继承BaseModel这个类自己写
# 作用：此处存储用户偏好（User Preferences），全局规章制度、跨会话的知识库、对某个用户的长期画像，跨线程共享数据等。
# 注意：此处只是示例，实际应用中应该持久化到数据库（PostgreSQL、Redis等）
STORE = InMemoryStore()



# PostgresSaver: 用于持久化 Agent 对话状态（State/Checkpoints）的组件，属于 Checkpointer。
# 作用：管理会话信息（Session），支持多轮对话短期记忆、Human-in-the-Loop（状态中断/审批）以及跨重启的对话恢复。
# 注意：它只负责当前 Thread（线程）的执行流和状态，不负责跨会话的长期记忆或用户偏好（User Preferences）。
# 类型：支持保存在内存（InMemory）和持久化（PostgreSQL）两种方式。
# ---------- PostgreSQL 配置（用于持久化 Agent 短期对话状态 State）----------
PG_HOST = os.getenv("PG_HOST", "localhost")
PG_PORT = int(os.getenv("PG_PORT", "5432"))
PG_USER = os.getenv("PG_USER", "postgres")
PG_PASSWORD = os.getenv("PG_PASSWORD", "")
PG_DBNAME = os.getenv("PG_DBNAME", "postgres")

_postgres_conn_str = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DBNAME}"

with PostgresSaver.from_conn_string(_postgres_conn_str) as CHECKPOINT:
    CHECKPOINT.setup()


# 技能 StoreBackend 命名空间（按 Agent scope 组织，无用户隔离）
SKILLS_STORE_NAMESPACE = ("skills",)


