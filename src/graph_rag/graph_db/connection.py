"""
Neo4j 连接管理 — 管理 Neo4j 驱动的连接池与会话生命周期。

功能：
    - 初始化 Neo4j Driver（连接池配置）
    - 获取同步/异步 Session
    - 连接健康检查
    - 优雅关闭（lifespan 管理）

配置来源：graph_rag/config.py（NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD）

使用方式：
    from graph_rag.graph_db.connection import get_session
    with get_session() as session:
        result = session.run(cypher_query)
"""
