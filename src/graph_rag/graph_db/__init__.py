"""
图数据库操作子模块 — 管理 Neo4j 连接与知识图谱。

✅ 全部已实现。包含三个子文件：
    - schema.py：图模型定义（11 种节点 + 11 种关系的 dataclass）
    - connection.py：Neo4j 连接管理（同步/异步双驱动，懒初始化，健康检查）
    - queries.py：Cypher 查询模板（3 个预定义模板 + LLM 生成查询）

知识图谱包含三个子图：
    1. 系统操作子图：Module → Function → Step → Requirement
    2. 法规关联子图：Regulation → Clause → Standard（+ ZoneType/EquipmentType 交叉关联）
    3. 设备依赖子图：Equipment → Equipment(依赖) → Zone

数据写入由 ingestion/entity_relation_extractor.py（❌ 骨架）和 ingestion/biz_sync.py（❌ 骨架）负责。
数据查询由 graph_traverser.py 通过 connection.py 执行。

⚠️ 已知问题：
    1. queries.py 中 query_llm() 调用 ainvoke() 缺少 await，会返回协程对象
    2. NODE_TYPES / REL_TYPES 在 entity_extractor.py 和 queries.py 中重复定义，
       应统一到 schema.py 中导出
"""

