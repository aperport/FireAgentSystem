
# 本地skills文件夹路径
from pathlib import Path
from agent.llm_config import DeepSeek_LLM
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
    "procurement-analyst": "procurement",
    "procurement-order": "order",
}

# 摘要模型
SUMMARY_MODEL = DeepSeek_LLM

# 记忆存储，此处存到了内存，实际应该持久化
STORE = InMemoryStore()


# 检查点
CHECKPOINT = MongoDBSaver(
    client=_mongodb_client,
    db_name=MONGODB_DB_NAME,
    checkpoint_collection_name=MONGODB_CHECKPOINT_COLLECTION,
)

# 技能 StoreBackend 命名空间（按 Agent scope 组织，无用户隔离）
SKILLS_STORE_NAMESPACE = ("skills",)
