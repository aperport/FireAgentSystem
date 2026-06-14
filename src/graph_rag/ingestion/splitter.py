"""
Markdown 切分模块 — 将解析后的 Markdown 文本切分为适合入库的片段。

切分策略：
    1. 标题切分：按 Markdown 标题层级（# / ## / ###）切分
    2. 语义切分：在标题切分基础上，对过长段落按语义边界二次切分
    3. 图片提取：识别图片标记（![alt](path)），提取路径和描述

切分后输出：
    - 文本片段 → embedding.py 向量化 → Milvus fire_doc_collection
    - 图片路径 → 多模态描述 → embedding.py → Milvus fire_image_collection

参考项目：Multimodal_RAG 的 splitters/splitter_md.py。
"""
