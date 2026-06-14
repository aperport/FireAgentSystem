"""
向量检索模块 — 基于 Milvus 实现知识库的语义检索。

支持三种检索策略：
    1. 稠密检索（dense）：Embedding 向量相似度，适合语义模糊查询
    2. 稀疏检索（sparse）：BM25 关键词匹配，适合条款号/设备型号等精确查询
    3. 混合检索（hybrid）：稠密+稀疏加权融合，兼顾语义和关键词，推荐默认使用

三个 Collection：
    - fire_doc_collection：静态知识文档（法规/标准/手册）
    - fire_context_collection：对话历史
    - fire_image_collection：图文混合文档

由 MCP Tool (knowledge_search) 和 orchestrator.py 调用。
"""
