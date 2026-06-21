"""
图数据库操作子模块 — 管理 Neo4j 连接与知识图谱。

包含三个子文件：
    - schema.py：图模型定义（节点标签 / 关系类型 / 属性约束）
    - connection.py：Neo4j 连接管理（连接池 / 会话生命周期）
    - queries.py：常用 Cypher 查询模板（按场景预定义）

知识图谱包含三个子图：
    1. 系统操作子图：Module → Function → Step → Requirement
    2. 法规关联子图：Regulation → Clause → Standard → ZoneType
    3. 设备依赖子图：Equipment → Equipment → Zone

数据写入由 ingestion/entity_relation_extractor.py 和 ingestion/biz_sync.py 负责。
数据查询由 graph_traverser.py 通过 connection.py 执行。
"""

