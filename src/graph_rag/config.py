"""
GraphRAG 配置模块 — 集中管理 GraphRAG 相关的所有配置项。

⚠️ 当前状态：空骨架，未实现。各模块自行读取环境变量或硬编码连接参数。

待实现配置项：
    Neo4j 连接：
        - NEO4J_URI          bolt://localhost:7687
        - NEO4J_USER         neo4j
        - NEO4J_PASSWORD     （从 .env 读取）
        - NEO4J_DATABASE     neo4j

    PostgreSQL + pgvector 连接：
        - PG_HOST            localhost
        - PG_PORT            5432
        - PG_USER            postgres
        - PG_PASSWORD        （从 .env 读取）
        - PG_DBNAME          fire_rag

    Embedding 模型：
        - EMBEDDING_MODEL    BAAI/bge-small-zh-v1.5（当前硬编码在 collections.py）
        - EMBEDDING_DEVICE   cuda（当前硬编码）

    DashScope API（ingestion/embedding.py 待实现时需要）：
        - DASHSCOPE_API_KEY
        - TEXT_EMBEDDING_MODEL    text-embedding-v4
        - MULTIMODAL_EMBEDDING_MODEL  multimodal-embedding-v1

    DotsOCR（ingestion/doc_parser/pdf_parser.py 待实现时需要）：
        - DOTS_OCR_URL

    检索参数：
        - DEFAULT_TOP_K          默认返回条数（当前各模块默认 5）
        - DEFAULT_GRAPH_DEPTH    图遍历默认深度
        - RAGAS_THRESHOLD        RAGAS 评估通过阈值（当前硬编码 0.7）
        - MIN_SIMILARITY         向量检索最低相似度（当前硬编码 0.3）
        - LLM_TIMEOUT            LLM 调用超时秒数（当前硬编码 2.0）

实现建议：
    1. 使用 pydantic-settings 的 BaseSettings，自动从 .env 读取
    2. 提供 get_settings() 单例，各模块统一从此处获取配置
    3. 消除 orchestrator.py 中硬编码的 PG 连接参数
    4. 消除 graph_traverser.py 中散落的 os.getenv() 调用
"""
