"""
向量数据库操作子模块 — 基于 PostgreSQL + pgvector 管理向量存储与检索。

包含三个子文件：
    - collections.py：PG 表 Schema 定义（DDL / 索引 / 查询模板 / 连接管理器）
    - db_operator.py：数据插入（文档片段写入 / 图片描述写入）
    - db_retriever.py：检索引擎（dense 检索由 PG pgvector 执行，sparse 检索由 Python rank_bm25 执行，hybrid 在 Python 层 RRF 融合）

两个向量表：
    fire_doc_collection     — 知识文档片段（法规、手册、巡检报告）
    fire_image_collection   — 图片多模态描述（设备照片 OCR 结果）

检索分工：
    - dense  → PG pgvector 余弦相似度（语义模糊查询）
    - sparse → Python jieba + rank_bm25（精确关键词，启动时从 PG 加载 text 重建索引）
    - hybrid → Python 层 RRF 融合 dense + sparse 结果

数据写入由 ingestion/doc_parser.py + ingestion/embedding.py 负责。
数据查询由 vector_retriever.py 通过 db_retriever.py 执行。
"""
