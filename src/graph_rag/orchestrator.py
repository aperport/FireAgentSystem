"""
GraphRAG 查询编排器 — 整个 GraphRAG Pipeline 的核心入口。

负责协调以下步骤：
    1. 实体抽取：从用户自然语言问题中提取关键实体
    2. 并行检索：向量检索(Milvus) + 图遍历(Neo4j) 同时进行
    3. 去重融合：合并向量片段与图路径，按相关性排序，截断至Token预算
    4. LLM生成：基于融合上下文生成结构化回答
    5. RAGAS评估：评估回答质量，不达标时走人工审批或兜底

对外接口：
    orchestrate(query: str, **kwargs) -> GraphRAGResult

由 MCP Tool (knowledge_tools.py 中的 graph_rag_search) 调用。
"""
