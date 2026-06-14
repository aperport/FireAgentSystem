"""
Milvus Collection Schema 定义 — 定义向量库中各 Collection 的字段结构。

共用 Schema（兼容文本和图文混合）：
    - id：VARCHAR 主键
    - text：VARCHAR 文本内容
    - category：VARCHAR 分类（regulation / standard / manual / faq）
    - source_file：VARCHAR 来源文件名
    - image_path：VARCHAR 图片路径（可选）
    - title：VARCHAR 标题/条款号
    - sparse_vector：SPARSE_FLOAT_VECTOR（BM25 稀疏向量）
    - dense_vector：FLOAT_VECTOR(1024)（稠密语义向量，DashScope text-embedding-v4）

本文件为 db_operator.py 的数据插入提供字段校验，
也为 db_retriever.py 的检索提供输出字段映射。
"""
