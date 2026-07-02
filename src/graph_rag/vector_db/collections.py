"""
向量数据库 Schema 定义 — 基于 PostgreSQL + pgvector 定义向量表的字段结构与索引。

✅ 已实现。两个向量表：
    1. fire_doc_collection   — 知识文档片段（法规、手册、巡检报告）
    2. fire_image_collection — 图片多模态描述（设备照片 OCR 结果）

检索策略（PG 只负责 dense 检索，BM25 由 Python 端 rank_bm25 独立构建）：
    - dense 检索：PG pgvector 余弦相似度（语义模糊查询）
    - sparse 检索：Python jieba + rank_bm25（精确关键词，启动时从 PG 加载 text 重建索引）
    - hybrid 检索：dense + sparse 在 Python 层 RRF 融合

共用字段：
    - id           SERIAL PRIMARY KEY
    - text         TEXT           文本内容（BM25 索引的数据源）
    - category     VARCHAR(50)    分类（regulation / standard / manual / faq）
    - source_file  VARCHAR(255)   来源文件hash
    - source_name  VARCHAR(255)   来源文件名
    - title        VARCHAR(255)   标题/条款号
    - dense_vector vector(512)    稠密语义向量（BAAI/bge-small-zh-v1.5，512维）

fire_image_collection 独有字段：
    - image_path     VARCHAR(512) 图片路径

本文件为 db_operator.py 的数据插入提供表创建与字段校验，
也为 db_retriever.py 的检索提供查询模板与输出字段映射。

⚠️ 已知问题：
    1. Embedding 模型名和设备硬编码（BAAI/bge-small-zh-v1.5 + cuda），
       应从 config.py 读取
    2. IVFFlat 索引 lists=100 在数据量小时效果差，应根据数据量动态调整
    3. 单例模式（__new__）在多数据库场景下不灵活

待优化：
    - Embedding 配置外部化
    - 向量索引参数自适应（根据数据量选择 lists 数量或切换到 HNSW）
"""

from pgvector.psycopg2 import register_vector
from util_tools.logger import get_logger
from langchain_huggingface import HuggingFaceEmbeddings
import psycopg2

logger = get_logger(__name__)


# ──────────────── 表定义（DDL）────────────────

# 知识文档表
FIRE_DOC_DDL = """
CREATE TABLE IF NOT EXISTS fire_doc_collection (
    id            SERIAL PRIMARY KEY,
    text          TEXT NOT NULL,
    category      VARCHAR(50),
    source_file   VARCHAR(255),
    source_name   VARCHAR(255),
    title         VARCHAR(255),
    dense_vector  vector(512),
    created_at    TIMESTAMP DEFAULT NOW()
);

-- 分类过滤索引
CREATE INDEX IF NOT EXISTS idx_doc_category ON fire_doc_collection (category);

-- 来源文件索引（父文档回填时按文件名查完整文档）
CREATE INDEX IF NOT EXISTS idx_doc_source_file ON fire_doc_collection (source_file);
"""

# 图片文档表
FIRE_IMAGE_DDL = """
CREATE TABLE IF NOT EXISTS fire_image_collection (
    id            SERIAL PRIMARY KEY,
    text          TEXT NOT NULL,
    category      VARCHAR(50),
    image_path    VARCHAR(512),
    source_file   VARCHAR(255),
    source_name   VARCHAR(255),
    title         VARCHAR(255),
    dense_vector  vector(512),
    created_at    TIMESTAMP DEFAULT NOW()
);

-- 来源文件索引
CREATE INDEX IF NOT EXISTS idx_image_source_file ON fire_image_collection (source_file);
"""

# 向量索引创建语句（数据入库后手动调用，空表建索引无意义）
FIRE_DOC_VECTOR_INDEX = """
CREATE INDEX IF NOT EXISTS idx_doc_dense ON fire_doc_collection
    USING ivfflat (dense_vector vector_cosine_ops) WITH (lists = 100);
"""

FIRE_IMAGE_VECTOR_INDEX = """
CREATE INDEX IF NOT EXISTS idx_image_dense ON fire_image_collection
    USING ivfflat (dense_vector vector_cosine_ops) WITH (lists = 100);
"""


# ──────────────── 查询模板 ────────────────

# 稠密检索（余弦相似度）
DENSE_SEARCH_SQL = """
SELECT id, text, category, source_file, title,
       1 - (dense_vector <=> %s) AS score
FROM {table_name}
WHERE 1=1
{category_filter}
ORDER BY dense_vector <=> %s
LIMIT %s
"""

# 按来源文件查询（父文档回填用）
GET_BY_SOURCE_FILE_SQL = """
SELECT id, text, category, source_file, title
FROM {table_name}
WHERE source_file = %s
ORDER BY id
"""

# 加载全部文本（BM25 索引重建用）
LOAD_ALL_TEXT_SQL = """
SELECT id, text, category, source_file, title
FROM fire_doc_collection
ORDER BY id
"""


# ──────────────── 数据库连接管理 ────────────────

class PGVectorManager:
    """PostgreSQL + pgvector 连接管理器

    职责：
        - 管理连接（单例模式）
        - 初始化表结构（DDL）
        - 提供游标
        - 优雅关闭

    使用方式：
        from graph_rag.vector_db.collections import PGVectorManager
        import os
        pg = PGVectorManager(
            host=os.getenv("PG_HOST", "localhost"),
            user=os.getenv("PG_USER", "postgres"),
            password=os.getenv("PG_PASSWORD", ""),
            dbname=os.getenv("PG_DBNAME", "fire_rag"),
        )
        pg.init_tables()  # 首次部署时调用
    """

    _instance = None

    def __new__(cls, host: str, user: str, password: str, dbname: str, port: int = 5432):
        """单例保护：已有实例时直接返回，避免重复创建连接"""
        if cls._instance is not None:
            return cls._instance
        return super().__new__(cls)

    def __init__(self, host: str, user: str, password: str, dbname: str, port: int = 5432,model_name: str = "BAAI/bge-small-zh-v1.5"):
        if PGVectorManager._instance is not None:
            return  # 已初始化过，跳过
        self.host = host
        self.user = user
        self.password = password
        self.dbname = dbname
        self.port = port
        self.conn: psycopg2.extensions.connection | None = None
        self.model_name = model_name
        self.embeddings = None
        self._connect()
        self._set_up_embeddings()
        PGVectorManager._instance = self  # 连接成功后才注册为单例

    def _connect(self):
        """建立连接并注册 pgvector 扩展"""
        try:
            self.conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                dbname=self.dbname,
            )
            self.conn.autocommit = True
            cur = self.conn.cursor()
            # 确保 pgvector 扩展已安装
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            register_vector(cur)
            logger.info(f"PostgreSQL + pgvector 连接成功: {self.host}:{self.port}/{self.dbname}")
        except Exception as e:
            logger.error(f"PostgreSQL 连接失败: {e}")
            raise
    
    def _set_up_embeddings(self):
        """设置 embeddings 模型"""
        logger.info(f"设置 embeddings 模型: {self.model_name}")
        self.embeddings = HuggingFaceEmbeddings(model_name=self.model_name,
                                                model_kwargs={"device": "cuda"},
                                                encode_kwargs={"normalize_embeddings": True})
        logger.info("embeddings 模型设置完成")

    def init_tables(self):
        """初始化所有向量表（首次部署时调用）"""
        assert self.conn is not None, "数据库未连接"
        cur = self.conn.cursor()
        cur.execute(FIRE_DOC_DDL)
        cur.execute(FIRE_IMAGE_DDL)
        logger.info("向量表初始化完成")

    def build_vector_indexes(self):
        """构建向量索引（数据入库后调用，空表建索引无意义）"""
        assert self.conn is not None, "数据库未连接"
        cur = self.conn.cursor()
        cur.execute(FIRE_DOC_VECTOR_INDEX)
        cur.execute(FIRE_IMAGE_VECTOR_INDEX)
        logger.info("向量索引构建完成")

    def get_cursor(self):
        """获取游标"""
        if self.conn is None or self.conn.closed:
            self._connect()
        assert self.conn is not None, "数据库未连接"
        cur = self.conn.cursor()
        register_vector(cur)
        return cur

    def close(self):
        """关闭连接"""
        if self.conn and not self.conn.closed:
            self.conn.close()
            logger.info("PostgreSQL 连接已关闭")
        PGVectorManager._instance = None
