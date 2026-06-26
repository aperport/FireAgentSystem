"""
GraphRAG 模块 — 消防后勤知识问答系统的核心检索引擎。

将向量数据库（Milvus）的语义检索能力与图数据库（Neo4j）的关联遍历能力融合，
为 fire-qa-assistant 子智能体提供 GraphRAG 检索服务。

核心流程：
    用户问题 → 实体抽取 → 并行检索(向量+图) → 去重融合 → LLM生成 → RAGAS评估

模块结构：
    - orchestrator.py          查询编排器（核心入口）
    - entity_extractor.py      实体抽取
    - graph_traverser.py       图遍历（三级降级路由）
    - vector_retriever.py      向量检索
    - context_fusion.py        去重融合
    - retrieval_evaluator.py   检索结果评估（评分驱动升级）
    - evaluator.py             RAGAS质量评估
    - graph_db/                图数据库操作
    - vector_db/               向量数据库操作
    - ingestion/               数据写入管线
"""
