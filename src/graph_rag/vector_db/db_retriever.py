"""
Milvus 检索引擎 — 提供稠密、稀疏、混合三种检索策略。

检索策略：
    1. dense（稠密检索）：基于 Embedding 向量相似度，适合语义模糊查询
    2. sparse（稀疏检索）：基于 BM25 关键词匹配，适合条款号/设备型号等精确查询
    3. hybrid（混合检索）：稠密+稀疏加权融合，兼顾语义和关键词，推荐默认使用

检索参数：
    - query：查询文本
    - search_type：dense / sparse / hybrid
    - top_k：返回条数
    - category：按分类过滤（regulation / standard / manual / faq）
    - score_threshold：最低相似度阈值

由 vector_retriever.py 调用，也直接服务于 MCP Tool (knowledge_search)。
"""
