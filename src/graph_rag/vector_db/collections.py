"""
向量数据库 Schema 定义 — 基于 PostgreSQL + pgvector 定义向量表的字段结构与索引。

✅ 已实现。两个向量表：
    1. fire_doc_collection   — 知识文档片段（法规、手册、巡检报告）
    2. fire_image_collection — 图片多模态描述（设备照片 OCR 结果）

检索策略（dense 走 PG；sparse 当前由 Python 端 rank_bm25 实现，
后续将切换为 pgvector 原生 sparsevec 字段，见下方「稀疏向量演进路线」）：
    - dense 检索：PG pgvector 余弦相似度（语义模糊查询）
    - sparse 检索：当前 Python jieba + rank_bm25（精确关键词）
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

═══════════════════════════════════════════════
稀疏向量演进路线（接口已预留，当前未启用）
═══════════════════════════════════════════════
PGV 已支持原生稀疏向量类型 sparsevec，后续将把稀疏向量存入相应字段、
改用 SQL 查询替代「启动时从 PG 加载全表 text 在内存构建 BM25 索引」。

已为本路线预留（启用前请勿删除）：
    1. 表结构：SPARSE_VECTOR_DDL — 为两张表添加 sparse_vector sparsevec 字段
    2. 写入：SPARSE_VECTOR_PLACEHOLDER — db_operator._insert_documents 预留的
       列拼接点（稀疏向量字面量格式 '{索引:值,索引:值}/维度'，索引从 1 起）
    3. 查询：SPARSE_SEARCH_SQL — sparsevec 余弦相似度检索模板
    4. 索引：FIRE_DOC_SPARSE_INDEX / FIRE_IMAGE_SPARSE_INDEX —
       sparsevec 仅支持 HNSW 索引（不支持 IVFFlat），非零元素上限 1000；
       稀疏向量建索引应使用 sparsevec_cosine_ops，与 dense 检索距离函数保持一致

⚠️ 已知问题：
    1. IVFFlat 索引 lists=100 在数据量小时效果差，应根据数据量动态调整
    2. Embedding 配置（模型名/设备）已外部化到 config.py + ingestion/embedding.py 单例

本文件为 db_operator.py 的数据插入提供表创建与字段校验，
也为 db_retriever.py 的检索提供查询模板与输出字段映射。
"""

from pgvector.psycopg2 import register_vector
import psycopg2
import psycopg2.extras

from util_tools.logger import get_logger

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


# ──────────────── 稀疏向量（sparsevec）预留 ────────────────
# PGV 原生稀疏向量路线。当前未启用（sparse 仍走内存 BM25），启用步骤：
#   1. 执行 SPARSE_VECTOR_DDL 加字段
#   2. db_operator 写入时拼接 SPARSE_VECTOR_PLACEHOLDER 列与 '{i:v}/dim' 字面量
#   3. db_retriever.sparse_search 按 SPARSE_SEARCH_SQL 查询
#   4. 入库后调用 build_sparse_vector_indexes() 建 HNSW 索引
#   5. 删除内存 BM25 整套机器（分词/停用词/重建/检索）

# 为两张表添加 sparse_vector 字段（幂等，可反复执行）
SPARSE_VECTOR_DDL = """
ALTER TABLE fire_doc_collection ADD COLUMN IF NOT EXISTS sparse_vector sparsevec;
ALTER TABLE fire_image_collection ADD COLUMN IF NOT EXISTS sparse_vector sparsevec;
"""

# 稀疏向量字面量占位符：INSERT 列拼接时追加在 dense_vector 之后
# 值格式：'{1:0.5,3:1.2}/512'（索引从 1 起，末尾 /总维度）
SPARSE_VECTOR_PLACEHOLDER = "%s::sparsevec"

# 稀疏向量 HNSW 索引（sparsevec 不支持 IVFFlat，仅 HNSW；非零元素上限 1000）
FIRE_DOC_SPARSE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_doc_sparse ON fire_doc_collection
    USING hnsw (sparse_vector sparsevec_cosine_ops);
"""

FIRE_IMAGE_SPARSE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_image_sparse ON fire_image_collection
    USING hnsw (sparse_vector sparsevec_cosine_ops);
"""


# ──────────────── 查询模板 ────────────────

# 稠密检索（余弦相似度）
DENSE_SEARCH_SQL = """
SELECT id, text, category, source_file, title,
       1 - (dense_vector <=> %s::vector) AS score
FROM {table_name}
WHERE 1=1
{category_filter}
ORDER BY dense_vector <=> %s::vector
LIMIT %s
"""

# 稀疏检索预留（sparsevec 余弦相似度，与 dense 同用 <=>）
# 启用时将 {sparse_vector_placeholder} 替换为 '%s::sparsevec' 查询字面量
SPARSE_SEARCH_SQL = """
SELECT id, text, category, source_file, title,
       1 - (sparse_vector <=> {sparse_vector_placeholder}) AS score
FROM {table_name}
WHERE 1=1
{category_filter}
ORDER BY sparse_vector <=> {sparse_vector_placeholder}
LIMIT %s
"""

# 加载全部文本（BM25 索引重建用；切换 sparsevec 路线后此查询随之删除）
LOAD_ALL_TEXT_SQL = """
SELECT id, text, category, source_file, title
FROM fire_doc_collection
ORDER BY id
"""


# ──────────────── 全局单例 ────────────────

_pg_instance: "PGVectorManager | None" = None


class PGVectorManager:
    """PostgreSQL + pgvector 连接管理器（纯连接层 + DDL 运维）

    职责：
        - 管理连接（连接/重连/游标/关闭）
        - 初始化表结构与索引（DDL）

    不再负责 Embedding 模型：向量化统一走
    graph_rag.ingestion.embedding.get_embedder() 全局单例，
    避免连接管理与模型推理两类异构资源互相耦合。

    使用方式：
        from graph_rag.vector_db.collections import get_pg_instance
        import os
        pg = get_pg_instance(
            host=os.getenv("PG_HOST", "localhost"),
            user=os.getenv("PG_USER", "postgres"),
            password=os.getenv("PG_PASSWORD", ""),
            dbname=os.getenv("PG_DBNAME", "fire_rag"),
        )
        pg.init_tables()  # 首次部署时调用
    """

    def __init__(self, host: str, user: str, password: str, dbname: str, port: int):
        self.host = host
        self.user = user
        self.password = password
        self.dbname = dbname
        self.port = port
        self.conn: psycopg2.extensions.connection | None = None
        self._connect()

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

    def init_tables(self):
        """初始化所有向量表（首次部署时调用）"""
        assert self.conn is not None, "数据库未连接"
        cur = self.conn.cursor()
        cur.execute(FIRE_DOC_DDL)
        cur.execute(FIRE_IMAGE_DDL)
        logger.info("向量表初始化完成")

    def init_sparse_columns(self):
        """为两张表添加 sparse_vector 字段（启用 sparsevec 路线时调用，幂等）"""
        assert self.conn is not None, "数据库未连接"
        cur = self.conn.cursor()
        cur.execute(SPARSE_VECTOR_DDL)
        logger.info("sparse_vector 字段已就绪（sparsevec 路线预留）")

    def build_vector_indexes(self):
        """构建 dense 向量索引（数据入库后调用，空表建索引无意义）"""
        assert self.conn is not None, "数据库未连接"
        cur = self.conn.cursor()
        cur.execute(FIRE_DOC_VECTOR_INDEX)
        cur.execute(FIRE_IMAGE_VECTOR_INDEX)
        logger.info("dense 向量索引构建完成")

    def build_sparse_vector_indexes(self):
        """构建 sparse 向量 HNSW 索引（sparsevec 路线启用后调用）。

        sparsevec 仅支持 HNSW（不支持 IVFFlat），非零元素需 ≤1000。
        """
        assert self.conn is not None, "数据库未连接"
        cur = self.conn.cursor()
        cur.execute(FIRE_DOC_SPARSE_INDEX)
        cur.execute(FIRE_IMAGE_SPARSE_INDEX)
        logger.info("sparse 向量 HNSW 索引构建完成")

    def get_cursor(self):
        """获取游标（返回字典式游标，支持 row["column"] 取值）"""
        if self.conn is None or self.conn.closed:
            self._connect()
        assert self.conn is not None, "数据库未连接"
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        register_vector(cur)
        return cur

    def close(self):
        """关闭连接"""
        if self.conn and not self.conn.closed:
            self.conn.close()
            logger.info("PostgreSQL 连接已关闭")


def get_pg_instance(
    host: str, user: str, password: str, dbname: str, port: int
) -> PGVectorManager:
    """获取 PGVectorManager 全局单例（懒加载）。

    首次调用时创建实例，后续调用返回同一实例。
    替代原先的 __new__ 单例模式，更清晰且易于测试。
    """
    global _pg_instance
    if _pg_instance is None:
        _pg_instance = PGVectorManager(
            host=host,
            user=user,
            password=password,
            dbname=dbname,
            port=port,
        )
    return _pg_instance
