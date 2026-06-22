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
from typing import Optional


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


# ──────────────── 节点属性定义 ────────────────
# 以下 dataclass 定义各节点类型的属性字段，
# 为 entity_relation_extractor.py 写入和 graph_traverser.py 查询提供结构约束。

# ── 系统操作子图 ──

@dataclass
class ModuleNode:
    """模块节点 — 系统功能模块（如：火灾报警模块、消防水系统模块）"""
    name: str                                    # 模块名称（唯一标识）
    description: Optional[str] = None            # 模块描述

@dataclass
class FunctionNode:
    """功能节点 — 模块下的具体功能（如：火警确认、联动启动）"""
    name: str                                    # 功能名称
    module_name: str                             # 所属模块名称
    description: Optional[str] = None            # 功能描述

@dataclass
class StepNode:
    """步骤节点 — 功能的操作步骤（如：1.接收信号 2.确认火警 3.启动联动）"""
    name: str                                    # 步骤名称
    step_order: int                              # 步骤顺序
    function_name: str                           # 所属功能名称
    description: Optional[str] = None            # 步骤描述

@dataclass
class RequirementNode:
    """前置条件节点 — 执行步骤所需的前置条件/要求"""
    name: str                                    # 条件名称
    step_name: str                               # 关联步骤名称
    description: Optional[str] = None            # 条件描述


# ── 法规关联子图 ──

@dataclass
class RegulationNode:
    """法规节点 — 消防法规/规范（如：《建筑设计防火规范》GB50016）"""
    name: str                                    # 法规名称
    code: Optional[str] = None                   # 法规编号（如：GB50016-2014）
    description: Optional[str] = None            # 法规描述

@dataclass
class ClauseNode:
    """条款节点 — 法规中的具体条款（如：第5.1.1条）"""
    name: str                                    # 条款号（如：第5.1.1条）
    content: Optional[str] = None                # 条款内容
    regulation_name: Optional[str] = None        # 所属法规名称

@dataclass
class StandardNode:
    """标准节点 — 被条款引用的技术标准（如：GB 17945-2010）"""
    name: str                                    # 标准名称
    code: Optional[str] = None                   # 标准编号
    description: Optional[str] = None            # 标准描述


# ── 分类与规格 ──

@dataclass
class ZoneTypeNode:
    """区域类型节点 — 建筑分区分类（如：高层住宅、地下车库、商业营业厅）"""
    name: str                                    # 区域类型名称
    risk_level: Optional[str] = None             # 风险等级
    description: Optional[str] = None            # 类型描述

@dataclass
class EquipmentTypeNode:
    """设备类型节点 — 设备分类规格（如：烟感探测器、喷淋头、消防泵）"""
    name: str                                    # 设备类型名称
    category: Optional[str] = None               # 设备大类（报警/灭火/疏散）
    description: Optional[str] = None            # 类型描述


# ── 实体实例（来自业务数据） ──

@dataclass
class EquipmentNode:
    """设备实例节点 — 具体设备台账（来自业务数据库同步）"""
    equipment_id: str                            # 设备ID（业务主键）
    name: str                                    # 设备名称
    equipment_type: Optional[str] = None         # 设备类型名称
    install_date: Optional[str] = None           # 安装日期
    status: Optional[str] = None                 # 设备状态（正常/故障/停用）

@dataclass
class ZoneNode:
    """区域实例节点 — 建筑分区（来自业务数据库同步）"""
    zone_id: str                                 # 区域ID（业务主键）
    name: str                                    # 区域名称
    zone_type: Optional[str] = None              # 区域类型名称
    building: Optional[str] = None               # 所属建筑
    floor: Optional[str] = None                  # 楼层
    risk_level: Optional[str] = None             # 风险等级