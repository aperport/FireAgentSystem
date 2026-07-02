"""
实体/关系抽取模块 — 从知识文档中抽取实体和关系写入 Neo4j 知识图谱。

❌ 未实现（骨架）。抽取目标：
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

待实现：
    1. 复用 entity_extractor.py 的通用抽取引擎（需先完成重构，增加 document 模式）
    2. 文档段落级抽取：按 ParsedDocument 的章节结构逐段抽取
    3. 规则辅助抽取：条款号正则匹配（第X条第X款、X.X.X节等）
    4. Neo4j MERGE 写入：使用 MERGE 避免重复节点，CREATE UNIQUE 避免重复关系
    5. 抽取结果校验：与 schema.py 中的节点/关系定义对齐
    6. 批量写入优化：UNWIND + 批量 MERGE 提升写入性能

依赖：
    - entity_extractor.py（重构后的通用抽取引擎）
    - graph_db/connection.py（Neo4j 连接）
    - graph_db/schema.py（节点/关系结构约束）
"""
