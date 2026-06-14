"""
Milvus 数据插入模块 — 将向量化后的文档片段写入 Milvus Collection。

支持的写入场景：
    1. 知识文档入库：doc_parser + splitter + embedding → fire_doc_collection
    2. 图片文档入库：图片提取 + 多模态描述 → fire_image_collection
    3. 对话历史入库：AI回复自动写入 → fire_context_collection

数据来源：
    - ingestion/doc_parser.py 解析后的 Markdown 文本
    - ingestion/embedding.py 生成的向量

写入格式遵循 collections.py 中定义的 Schema。
"""
