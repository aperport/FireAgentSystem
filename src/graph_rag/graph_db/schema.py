"""
知识图谱模型定义 — 定义 Neo4j 中的节点标签、关系类型和属性约束。

节点类型（11种）：
    Module, Function, Step, Requirement — 系统操作子图
    Regulation, Clause, Standard — 法规关联子图
    ZoneType, EquipmentType — 分类与规格
    Equipment, Zone — 实体实例（来自业务数据）

关系类型（11种）：
    包含功能, 操作步骤, 下一步, 前置条件 — 系统操作子图
    包含条款, 引用, 适用法规, 要求配置 — 法规关联子图
    属于分类, 安装于, 依赖(供电/控制) — 设备依赖子图

本文件为 graph_traverser.py 的 Cypher 查询提供标签和关系名称常量，
也为 ingestion/entity_relation_extractor.py 的数据写入提供结构约束。
"""


from dataclasses import dataclass


# 节点类型
