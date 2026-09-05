"""
知识图谱模型定义 — 定义 Neo4j 中的节点标签、关系类型和属性约束。

✅ 已实现。节点类型（11种）：
    Module, Function, Step, Requirement — 系统操作子图
    Regulation, Clause, Standard — 法规关联子图
    ZoneType, EquipmentType — 分类与规格
    Equipment, Zone — 实体实例（来自业务数据）

关系类型（11种）：
    包含功能, 操作步骤, 下一步, 前置条件 — 系统操作子图
    包含条款, 引用, 适用法规, 要求配置 — 法规关联子图
    属于分类, 安装于, 依赖(供电/控制) — 设备依赖子图

（使用原生 neo4j 驱动时，此处类型不对查询产生影响，仅作参考和文档约束）

本文件为 graph_traverser.py 的 Cypher 查询提供标签和关系名称常量，
也为 ingestion/entity_relation_extractor.py 的数据写入提供结构约束。

⚠️ 已知问题：
    1. ~~NODE_TYPES / REL_TYPES 字典在 entity_extractor.py 和 queries.py 中
       各自重复定义了一份，应统一到本文件导出~~ ✅ 已统一
    2. dataclass 仅作结构约束，未与 Neo4j 实际写入/查询绑定，
       ingestion 写入管线实现后需验证字段是否与实际图数据一致

待优化：
    - ~~将 NODE_TYPES / REL_TYPES 常量统一到本文件，消除重复定义~~ ✅ 已完成
    - 增加 Schema 验证方法：写入前校验节点/关系是否符合定义
    - 增加 Schema 版本管理：图结构变更时支持迁移
"""


from dataclasses import dataclass
from typing import Optional
from util_tools.logger import get_logger

logger = get_logger(__name__)

# ──────────────── Schema 常量（统一导出，消除重复定义）────────────────
# ponytail: 之前在 entity_extractor.py / queries.py 各自定义了一份，统一到此处

NODE_TYPES = {
    "Module": "系统功能模块（如：值班、巡检、维修）",
    "Function": "模块下的具体功能",
    "Step": "功能的操作步骤",
    "Requirement": "执行步骤所需的前置条件/要求",
    "Regulation": "消防法规/规范（如：《建筑设计防火规范》GB50016）",
    "Clause": "法规中的具体条款（如：第5.1.1条）",
    "Standard": "被条款引用的技术标准（如：GB 17945-2010）",
    "ZoneType": "建筑分区分类（如：高层住宅、地下车库、ICU病房）",
    "EquipmentType": "设备分类规格（如：烟感探测器、喷淋头、消防泵）",
    "Equipment": "具体设备实例（如：烟感探测器-01、EPS电源-01）",
    "Zone": "建筑区域实例（如：B栋3层、地下车库A区）",
}

REL_TYPES = {
    "包含功能": "Module → Function",
    "操作步骤": "Function → Step",
    "下一步": "Step → Step",
    "前置条件": "Step → Requirement",
    "包含条款": "Regulation → Clause",
    "引用": "Clause → Standard",
    "适用法规": "ZoneType → Regulation",
    "要求配置": "Clause → EquipmentType",
    "属于分类": "Equipment → EquipmentType",
    "安装于": "Equipment → Zone",
    "依赖": "Equipment → Equipment（供电/控制）",
}

# ──────────────── 节点属性定义 ────────────────
# 以下 dataclass 定义各节点类型的属性字段，
# 为 entity_relation_extractor.py 写入和 graph_traverser.py 查询提供结构约束。

# ── 系统操作子图 ──


@dataclass
class ModuleNode:
    """模块节点 — 系统功能模块（系统模块：值班、巡检等）"""
    name: str                                    # 模块名称（唯一标识）
    description: Optional[str] = None            # 模块描述


@dataclass
class FunctionNode:
    """功能节点 — 模块下的具体功能（）"""
    name: str                                    # 功能名称
    module_name: str                             # 所属模块名称
    description: Optional[str] = None            # 功能描述


@dataclass
class StepNode:
    """步骤节点 — 功能的操作步骤（）"""
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


# [删除理由] 11 个关系 dataclass（ContainsFunctionRel, HasStepRel, NextStepRel,
# PrerequisiteRel, ContainsClauseRel, ReferencesRel, ApplicableRegulationRel,
# RequiresConfigRel, BelongsToCategoryRel, InstalledInRel, DependsOnRel）已删除。
# 原因：writer.py 的 _build_merge_rel_cypher() 直接从 REL_TYPES 字典生成 Cypher，
# 不读取这些 dataclass。它们在整个代码库中无任何引用方，属于死代码。
# 关系的结构约束已由 REL_TYPES 字典和 validate_extract_result() 充分表达。
