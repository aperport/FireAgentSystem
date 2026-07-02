"""
GraphRAG 模块 — 消防后勤知识问答系统的核心检索引擎。

将向量数据库（PostgreSQL + pgvector）的语义检索能力与图数据库（Neo4j）的关联遍历能力融合，
为 fire-qa-assistant 子智能体提供 GraphRAG 检索服务。

核心流程：
    用户问题 → 实体抽取 → 并行检索(向量+图) → 去重融合 → 返回上下文

查询管线（已实现）：
    orchestrator.py          查询编排器（核心入口）
        ├── entity_extractor.py   实体抽取（LLM + NER 并行融合）
        ├── vector_retriever.py   向量检索统一入口
        │   └── vector_db/        向量数据库操作（PG pgvector + BM25 + RRF）
        ├── graph_traverser.py    图遍历（三级降级路由：模板→类型反查→LLM生成）
        │   └── graph_db/         图数据库操作（Neo4j 连接/查询/Schema）
        ├── context_fusion.py     去重融合（转换→去重→排序→父文档回填→Token截断）
        ├── retrieval_evaluator.py 检索结果判空（未接入编排器）
        └── json_save.py          结果持久化（JSON 追加写入）

评估模块（已实现）：
    evaluator.py              RAGAS 质量评估（⚠️ 缺少 ragas 包导入）

写入管线（大部分未实现）：
    ingestion/
        ├── doc_parser/md_parser.py   Markdown 解析（✅ 已实现）
        ├── doc_parser/dispatcher.py  格式路由（❌ 骨架）
        ├── doc_parser/pdf_parser.py  PDF 解析（❌ 骨架）
        ├── doc_parser/image_parser.py 图片解析（❌ 骨架）
        ├── doc_parser/office_parser.py Word/HTML 解析（❌ 骨架）
        ├── splitter.py               文本切分（❌ 骨架）
        ├── embedding.py              向量化（❌ 骨架）
        ├── entity_relation_extractor.py 实体关系抽取（❌ 骨架）
        └── biz_sync.py              业务数据同步（❌ 骨架）

配置模块（未实现）：
    config.py                 集中配置管理（❌ 空骨架，当前各模块自行读取环境变量）

待实现 / 待修复：
    1. config.py：实现集中配置，消除各模块硬编码和散落的环境变量读取
    2. orchestrator.py：PG 连接参数改为从 config 读取；单例复用
    3. evaluator.py：补充 ragas 包导入（Dataset, Faithfulness, AnswerRelevancy 等）
    4. retrieval_evaluator.py：接入 orchestrator 的检索流程，实现空结果自动 fallback
    5. ingestion/doc_parser/example.py：属于食谱领域，与消防场景无关，建议移除或替换
    6. ingestion 写入管线：dispatcher → 各 parser → splitter → embedding → 写入
    7. graph_db/queries.py + entity_extractor.py：NODE_TYPES/REL_TYPES 重复定义，应统一到 schema.py
"""
