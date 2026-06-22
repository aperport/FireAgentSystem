"""
图遍历模块 — 基于 Neo4j Cypher 查询实现知识图谱的关联遍历。

以实体抽取结果为起点，沿关系路径扩展 N 跳，获取结构化的关联上下文。

三种典型遍历场景：
    1. 系统操作导航：Module → Function → Step → Requirement
    2. 法规关联检索：ZoneType → Regulation → Clause → Standard
    3. 设备依赖追踪：Equipment → Equipment(依赖) → Zone
    
遍历深度、关系类型过滤等参数由 orchestrator.py 传入。

由 MCP Tool (graph_query) 和 orchestrator.py 调用。
"""
