"""
图数据库子模块 — Neo4j 知识图谱的 schema / 连接 / 查询 / 写入。

═══════════════════════════════════════════════════════════════
整体架构
═══════════════════════════════════════════════════════════════

graph_db/
├── schema.py      图模型定义（11 节点 + 11 关系 dataclass）
├── connection.py  Neo4j 连接管理（同步/异步双驱动，懒初始化）
├── queries.py     Cypher 查询（3 模板 + LLM 动态生成）
└── writer.py      批量写入器（UNWIND+MERGE，Cypher 从 schema 自动生成）

知识图谱三个子图：
    1. 系统操作子图：Module → Function → Step → Requirement
    2. 法规关联子图：Regulation → Clause → Standard（+ ZoneType/EquipmentType 交叉）
    3. 设备依赖子图：Equipment → Equipment(依赖) → Zone

═══════════════════════════════════════════════════════════════
数据写入调用链（文档 → Neo4j）
═══════════════════════════════════════════════════════════════

  Markdown 文件
       │
       ▼
  ingestion/doc_parser/md_parser.py   MdParser.parse() → ParsedDocument
       │
       ▼
  ingestion/splitter.py               split() → (text_chunks, image_docs)
       │
       ├──► ingestion/embedding.py    aembed_documents() → 向量
       │         │
       │         ▼
       │    vector_db/db_operator.py   DBOperator.insert_chunks() → PG
       │
       └──► ingestion/entity_relation_extractor.py
                 │
                 │  extract_and_write_document()  ← 一站式入口
                 │    内部调用: EntityExtractor → schema.validate → writer
                 │
                 ▼
            graph_db/writer.py          Neo4jBatchWriter.write_nodes()
                                      Neo4jBatchWriter.write_relations()
                 │
                 ▼
              Neo4j

═══════════════════════════════════════════════════════════════
直接存储文档的方法
═══════════════════════════════════════════════════════════════

  ✅ 推荐入口（实体+关系提取 + 自动写入 Neo4j）：

    from graph_rag.ingestion.entity_relation_extractor import extract_and_write_document

    await extract_and_write_document(
        paragraphs: list[str],       # 文档段落列表
        llm_client,                  # LLM 客户端（需支持 ainvoke）
        writer=None,                 # Neo4jBatchWriter，None 则自动创建
        doc_name="文档名",           # 用于日志
    )
    # → 返回 (entities, relations)，同时已写入 Neo4j

  ✅ 单段落提取+写入：

    from graph_rag.ingestion.entity_relation_extractor import extract_and_write_paragraph

    await extract_and_write_paragraph(
        paragraph: str,
        llm_client,
        writer=None,
        doc_name="文档名",
    )

  ✅ 底层写入（已有 Entity/Relation 对象，直接入库）：

    from graph_rag.graph_db.writer import Neo4jBatchWriter

    w = Neo4jBatchWriter()           # 默认读 NEO4J_URI/USER/PASSWORD 环境变量
    await w.write_nodes(entities)    # 必须先写节点
    await w.write_relations(relations)  # 再写关系

═══════════════════════════════════════════════════════════════
数据查询调用链（查询 → Neo4j → 结果）
═══════════════════════════════════════════════════════════════

  用户查询
       │
       ▼
  orchestrator.py   GraphRAGOrchestrator.rag_search()
       │
       ├──► entity_extractor.py      EntityExtractor.main_pip() → ExtractResult
       ├──► vector_retriever.py      VectorRetriever.search() → PG 向量检索
       ├──► graph_traverser.py       GraphTraverser.traverse()
       │         └──► queries.py     模板查询 → 类型回填 → LLM 生成 Cypher
       └──► context_fusion.py        去重 + 排序 + 截断

═══════════════════════════════════════════════════════════════
⚠️ 已知问题
═══════════════════════════════════════════════════════════════

    1. ❌ 无顶层 ingestion 编排函数（parser→splitter→embed→extract→write 未串联）
       → 需手动按上述调用链逐步调用，或自行编排
    2. ❌ doc_parser/dispatcher.py 未实现，仅支持 Markdown
    3. ❌ ingestion/biz_sync.py 未实现，设备依赖子图无数据来源
    4. ❌ config.py 为空，连接参数散落在各模块 os.getenv()
    5. ⚠️ retrieval_evaluator.py / evaluator.py 已实现但未接入 orchestrator
    6. ⚠️ graph_traverser.py traverse() 只处理第一个 entity 即返回
    7. ✅ queries.py query_llm() await 问题已修复
    8. ✅ NODE_TYPES/REL_TYPES 已统一到 schema.py


补充：
图数据库修改思路：
关于图数据库查询，可使用 Neo4j 的 Cypher 语言进行二跳查询。并将结果一并返回（许多条），之后对结果进行拼接凑成完整话语（一般是：A 属性 B，需要对属性进行映射，然后拼接，如 A 同事 B ，可用同事 拼接 A的同事是B。
）之后将拼接的结果，分别使用向量化（稠密向量），之后比对查询语句，进行匹配，之后按照分数排序，将得分最高的结果作为向量查询结果返回
"""
