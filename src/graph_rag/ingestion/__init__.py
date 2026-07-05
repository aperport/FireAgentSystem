"""
数据写入管线子模块 — 将知识文档写入 PostgreSQL + Neo4j。

管线流程（MD 路线）：
    MD 文件 → doc_parser.md_parser → ParsedDocument
        → text  → splitter → embedding → fire_doc_collection (PG)
        → images → alt/OCR 文本 → embedding → fire_image_collection (PG)
        → text  → entity_relation_extractor → Neo4j

═══════════════════════════════════════════════════════════════
顶层编排函数
═══════════════════════════════════════════════════════════════

  ✅ ingest_markdown()    单文件入库（PG 向量 + Neo4j 知识图谱）
  ✅ ingest_directory()   目录批量入库

  用法：
    from graph_rag.ingestion import ingest_markdown, ingest_directory

    # 单文件
    result = await ingest_markdown("docs/防火规范.md")

    # 整个目录
    results = await ingest_directory("docs/")

═══════════════════════════════════════════════════════════════
内部调用链（ingest_markdown 内部自动执行）
═══════════════════════════════════════════════════════════════

  1. MdParser.parse(file_path)           → ParsedDocument
  2. split(parsed_doc)                   → (text_chunks, image_docs)
  3. DBOperator.insert_chunks(text_chunks)     → PG fire_doc_collection
     DBOperator.insert_picture(image_docs)      → PG fire_image_collection
  4. extract_and_write_document(paragraphs)     → Neo4j（实体 + 关系）

═══════════════════════════════════════════════════════════════
可单独调用的子步骤
═══════════════════════════════════════════════════════════════

  仅解析：   MdParser().parse(path)           → ParsedDocument
  仅切分：   split(parsed_doc)                → (text_chunks, image_docs)
  仅写PG：  DBOperator().insert_chunks(chunks)
  仅写Neo4j：extract_and_write_document(paragraphs, llm_client)
"""


