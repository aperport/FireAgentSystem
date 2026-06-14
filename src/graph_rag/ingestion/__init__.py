"""
数据写入管线子模块 — 将多模态知识文档和业务数据写入 Milvus + Neo4j。

子模块结构：
    doc_parser/       多模态文档解析（PDF/Word/PNG/MD → 统一格式）
        dispatcher.py     格式识别与引擎路由
        pdf_parser.py     PDF解析（DotsOCR + 嵌入图片提取）
        image_parser.py   图片解析（OCR + 多模态LLM描述）
        office_parser.py  Word/HTML解析（Unstructured）
        md_parser.py      Markdown直接读取

    splitter.py               Markdown 切分（标题+语义+图片提取）
    embedding.py              文本/多模态向量化（DashScope）
    entity_relation_extractor.py  实体/关系抽取（文档 → Neo4j 知识图谱）
    biz_sync.py               业务数据同步（Java DB → Neo4j 设备依赖子图）

管线流程：
    多模态文档 → doc_parser → ParsedDocument
        → text → splitter → embedding → Milvus
        → images → 多模态描述 → embedding → Milvus
        → text → entity_relation_extractor → Neo4j
    业务数据 → biz_sync → Neo4j
"""
