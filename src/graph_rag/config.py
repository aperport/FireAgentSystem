"""
GraphRAG 配置模块 — 集中管理 GraphRAG 相关的所有配置项。

配置项包括：
    - Neo4j 连接（URI / 用户名 / 密码）
    - Milvus 连接（Host / Port）
    - DashScope Embedding（API Key / 模型名）
    - DotsOCR（服务地址）
    - 检索参数（默认Top-K / 图遍历默认深度 / RAGAS阈值）

所有敏感信息从 .env 读取，不硬编码。
"""
