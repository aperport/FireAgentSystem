"""
数据写入管线子模块 — 将多模态知识文档和业务数据写入 PostgreSQL + Neo4j。

实现状态概览：

    doc_parser/               多模态文档解析（PDF/Word/PNG/MD → 统一格式）
        ✅ md_parser.py          Markdown 直接读取（已实现：标准化+元数据增强+图片提取）
        ❌ dispatcher.py         格式识别与引擎路由（骨架）
        ❌ pdf_parser.py         PDF 解析（骨架：DotsOCR + VLLM）
        ❌ image_parser.py       图片解析（骨架：OCR + 多模态 LLM 描述）
        ❌ office_parser.py      Word/HTML 解析（骨架：Unstructured）
        ⚠️ example.py            数据准备模块（已实现，但属于食谱领域，与消防场景无关）

    ❌ splitter.py               文本切分（骨架：标题切分+语义二次切分+图片分离）
    ❌ embedding.py              向量化（骨架：DashScope text-embedding-v4 / multimodal-embedding-v1）
    ❌ entity_relation_extractor.py  实体/关系抽取（骨架：文档 → Neo4j 知识图谱）
    ❌ biz_sync.py               业务数据同步（骨架：Java DB → Neo4j 设备依赖子图）

管线流程：
    多模态文档 → doc_parser → ParsedDocument
        → text  → splitter → embedding → fire_doc_collection (PG)
        → images → 多模态描述 → embedding → fire_image_collection (PG)
        → text  → entity_relation_extractor → Neo4j
    业务数据 → biz_sync → Neo4j

待实现优先级：
    1. dispatcher.py — 格式路由是整个写入管线的入口
    2. splitter.py — 切分是向量化入库的关键步骤
    3. embedding.py — 向量化是向量检索的前提
    4. entity_relation_extractor.py — 图谱构建依赖此模块
    5. pdf_parser.py / image_parser.py / office_parser.py — 各格式解析器
    6. biz_sync.py — 业务数据同步

⚠️ 注意：当前 docstring 中部分位置仍引用 Milvus，实际实现使用 PostgreSQL + pgvector。
"""
