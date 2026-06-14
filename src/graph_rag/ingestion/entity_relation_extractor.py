"""
实体/关系抽取模块 — 从知识文档中抽取实体和关系写入 Neo4j 知识图谱。

抽取目标：
    1. 法规关联子图：
        - 法规名 → Regulation 节点
        - 条款号/内容 → Clause 节点
        - 条款引用关系 → 引用 边
        - 适用场所类型 → 适用法规 边
        - 设备配置要求 → 要求配置 边

    2. 系统操作子图：
        - 模块名 → Module 节点
        - 功能名 → Function 节点
        - 操作步骤 → Step 节点
        - 前置条件 → Requirement 节点

抽取方式：
    - LLM 结构化输出提取（使用 with_structured_output 保证输出格式）
    - 规则辅助（条款号格式识别：第X条第X款、X.X节等）

抽取结果写入 Neo4j（通过 graph_db/connection.py）。
"""
