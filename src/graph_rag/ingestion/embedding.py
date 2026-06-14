"""
Embedding 向量化模块 — 将文本片段转化为向量用于 Milvus 检索。

支持两种向量化：
    1. 文本 Embedding：DashScope text-embedding-v4，1024维，中文效果好
    2. 多模态 Embedding：DashScope multimodal-embedding-v1，含图片文档的向量化

包含限流机制：
    - DashScope API 有调用频率限制，需在批量入库时控制请求速率
    - 参考 Multimodal_RAG 的 utils/embeddings_utils.py 的限流实现

向量化结果写入 Milvus（通过 vector_db/db_operator.py）。
"""
