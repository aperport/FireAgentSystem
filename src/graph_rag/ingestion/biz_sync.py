"""
业务数据同步模块 — 将 Java 后端业务数据库的结构化数据同步到 Neo4j。

同步内容（仅写入设备依赖子图）：
    1. 设备台账 → Equipment 节点（id, name, install_date, status）
    2. 建筑分区 → Zone 节点 + ZoneType 节点（name, building, floor, risk_level）
    3. 设备依赖关系 → 依赖 边（供电给 / 控制 / 联动）
    4. 设备安装位置 → 安装于 边

不同步的内容（留在关系型DB）：
    - 时序数据（能耗读数、报警流水）— 适合 SQL 聚合，图结构反而低效
    - 巡检/维修/值班等业务流水 — 这些是事件而非实体关系

同步方式：
    - 增量同步：Java后端业务变更时通过消息队列或定时任务触发
    - 全量同步：初次部署时批量导入

配置来源：graph_rag/config.py（JAVA_API_BASE_URL）
"""
