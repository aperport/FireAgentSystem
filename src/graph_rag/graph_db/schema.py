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
@dataclass
class system_operation:
    module: str = "Module"
    function: str = "Function"
    step: str = "Step"
    requirement: str = "Requirement"
    regulation: str = "Regulation"
    notes: str = "Notes"                                        # 注意事项

@dataclass
class regulation:
    clause: str = "Clause"
    standard: str = "Standard"
    zone_type: str = "ZoneType"
    equipment_type: str = "EquipmentType"
    equipment: str = "Equipment"
    zone: str = "Zone"
    section: str = "Section"                                    # 法规章节节点
    responsible_unit: str = "ResponsibleUnit"                   # 责任单位节点
    fire_hazard: str = "FireHazard"                             # 火灾隐患节点
    penalty: str = "Penalty"                                    # 处罚措施节点

@dataclass
class Equipment:
    category: str = "category"
    status: str = "status"
    location: str = "location"
    name: str = "name"



# 关系类型
@dataclass
class system_operation_relationship:
    rel_contains: str = "包含"
    rel_next_step: str = "下一步"
    rel_has_precondition: str = "前置条件为"
    rel_executed_by: str = "执行角色"
@dataclass
class regulation_relationship:
    issued_by: str = "发布主体"
    applies_to_region: str = "适用地域"
    applies_to_field: str = "适用领域"
    replaces: str = "修订替代"
    amends: str = "局部修订"
    abolishes: str = "废止失效"
    contains = "包含"         # 法规内部层级
    references = "引用"       # 跨文件/跨条款援引
@dataclass
class equipment_relationship:
    depends_on: str = "depends_on"
    installed_in: str = "installed_in"