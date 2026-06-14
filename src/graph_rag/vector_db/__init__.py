"""
向量数据库操作子模块 — 管理 Milvus 连接与向量检索。

包含三个子文件：
    - collections.py：Collection Schema 定义（字段/索引/向量维度）
    - db_operator.py：数据插入（文档片段写入 / 图片描述写入 / 对话历史写入）
    - db_retriever.py：检索引擎（稠密/稀疏/混合三种策略）

三个 Collection：
    fire_doc_collection     — 静态知识文档
    fire_context_collection — 对话历史
    fire_image_collection   — 图文混合

数据写入由 ingestion/doc_parser.py + ingestion/embedding.py 负责。
数据查询由 vector_retriever.py 通过 db_retriever.py 执行。
"""
