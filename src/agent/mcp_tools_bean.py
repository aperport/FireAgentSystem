"""
消防后勤 MCP 工具数据模型 — 定义各 MCP Tool 的请求/响应 Pydantic 模型。

原项目为采购场景（SupplierQueryInput/PartQueryInput/OrderInput等），
新项目替换为消防后勤场景。

分组名称常量：
    GROUP_FIRE_EQUIPMENT   — 设备分组
    GROUP_FIRE_ALARM       — 火警分组
    GROUP_FIRE_INSPECTION  — 巡检分组
    GROUP_FIRE_MAINTENANCE — 维修维保分组
    GROUP_FIRE_DUTY        — 值班分组
    GROUP_FIRE_UTILITY     — 能耗分组
    GROUP_KNOWLEDGE        — 知识检索分组
    GROUP_REPORT           — 报表评鉴分组
"""

from pydantic import BaseModel, Field
from typing import Optional


# ============================================================
# 分组名称常量
# ============================================================

GROUP_FIRE_EQUIPMENT = "fire_equipment"
GROUP_FIRE_ALARM = "fire_alarm"
GROUP_FIRE_INSPECTION = "fire_inspection"
GROUP_FIRE_MAINTENANCE = "fire_maintenance"
GROUP_FIRE_DUTY = "fire_duty"
GROUP_FIRE_UTILITY = "fire_utility"
GROUP_KNOWLEDGE = "knowledge"
GROUP_REPORT = "report"


# ============================================================
# 设备查询 — fire_equipment_query
# ============================================================

class FireEquipmentQueryInput(BaseModel):
    """消防设备查询请求"""
    name: Optional[str] = Field(None, description="设备名称（模糊查询）")
    location: Optional[str] = Field(None, description="安装位置（如 B栋3层）")
    category: Optional[str] = Field(None, description="设备分类：火灾探测类/报警类/灭火类/通风排烟类/疏散类/电气类")

class FireEquipmentItem(BaseModel):
    """消防设备信息"""
    id: str = Field(..., description="设备编号")
    name: str = Field(..., description="设备名称")
    location: str = Field(..., description="安装位置")
    category: str = Field(..., description="设备分类")
    status: str = Field(..., description="当前状态：正常/故障/停用/维修中")
    install_date: Optional[str] = Field(None, description="安装日期")
    last_check_date: Optional[str] = Field(None, description="最近检测日期")

class FireEquipmentQueryResult(BaseModel):
    """消防设备查询结果"""
    total: int = Field(..., description="匹配总数")
    items: list[FireEquipmentItem] = Field(default_factory=list, description="设备列表")


# ============================================================
# 火警/故障记录 — fire_alarm_record_query
# ============================================================

class FireAlarmRecordQueryInput(BaseModel):
    """火警/故障记录查询请求"""
    start_date: Optional[str] = Field(None, description="起始日期 yyyy-MM-dd")
    end_date: Optional[str] = Field(None, description="结束日期 yyyy-MM-dd")
    status: Optional[str] = Field(None, description="报警状态：待处理/处理中/已恢复")
    building: Optional[str] = Field(None, description="建筑区域")
    alarm_type: Optional[str] = Field(None, description="报警类型：火警/故障/预警")

class FireAlarmRecordItem(BaseModel):
    """火警/故障报警记录"""
    id: str = Field(..., description="报警记录编号")
    alarm_time: str = Field(..., description="报警时间")
    equipment_name: str = Field(..., description="报警设备名称")
    alarm_type: str = Field(..., description="报警类型：火警/故障/预警")
    status: str = Field(..., description="状态：待处理/处理中/已恢复")
    location: str = Field(..., description="报警设备位置")
    handler: Optional[str] = Field(None, description="处理人")
    recover_time: Optional[str] = Field(None, description="恢复时间")

class FireAlarmRecordQueryResult(BaseModel):
    """火警/故障记录查询结果"""
    total: int = Field(..., description="匹配总数")
    items: list[FireAlarmRecordItem] = Field(default_factory=list, description="报警记录列表")


# ============================================================
# 巡检查询 — fire_inspection_query
# ============================================================

class FireInspectionQueryInput(BaseModel):
    """巡检查询请求"""
    building: Optional[str] = Field(None, description="建筑区域")
    floor: Optional[str] = Field(None, description="楼层")
    period: Optional[str] = Field(None, description="时间范围")
    status: Optional[str] = Field(None, description="巡检状态：待执行/已完成/逾期/跳过")

class FireInspectionItem(BaseModel):
    """巡检记录"""
    id: str = Field(..., description="巡检任务编号")
    task_name: str = Field(..., description="巡检任务名称")
    executor: str = Field(..., description="执行人")
    building: str = Field(..., description="巡检区域")
    status: str = Field(..., description="状态：待执行/已完成/逾期/跳过")
    completed_at: Optional[str] = Field(None, description="完成时间")
    check_items_count: int = Field(0, description="检查项总数")
    abnormal_count: int = Field(0, description="异常发现数")

class FireInspectionQueryResult(BaseModel):
    """巡检查询结果"""
    total: int = Field(..., description="匹配总数")
    items: list[FireInspectionItem] = Field(default_factory=list, description="巡检记录列表")


# ============================================================
# 维修/维保工单 — fire_maintenance_order_query
# ============================================================

class FireMaintenanceOrderQueryInput(BaseModel):
    """维修/维保工单查询请求"""
    order_id: Optional[str] = Field(None, description="工单编号（精确查询）")
    status: Optional[str] = Field(None, description="工单状态：待派单/已派单/维修中/已完成/已验收/已取消")
    type: Optional[str] = Field(None, description="工单类型：维修/维保")
    building: Optional[str] = Field(None, description="建筑区域")

class FireMaintenanceOrderItem(BaseModel):
    """维修/维保工单"""
    order_id: str = Field(..., description="工单编号")
    type: str = Field(..., description="工单类型：维修/维保")
    equipment_name: str = Field(..., description="设备名称")
    status: str = Field(..., description="工单状态")
    building: str = Field(..., description="建筑区域")
    dispatcher: Optional[str] = Field(None, description="派工人")
    created_at: Optional[str] = Field(None, description="创建时间")
    completed_at: Optional[str] = Field(None, description="完成时间")
    description: Optional[str] = Field(None, description="问题描述")

class FireMaintenanceOrderQueryResult(BaseModel):
    """维修/维保工单查询结果"""
    total: int = Field(..., description="匹配总数")
    items: list[FireMaintenanceOrderItem] = Field(default_factory=list, description="工单列表")


# ============================================================
# 值班排班 — fire_duty_schedule_query
# ============================================================

class FireDutyScheduleQueryInput(BaseModel):
    """值班排班查询请求"""
    date: Optional[str] = Field(None, description="查询日期 yyyy-MM-dd")
    shift: Optional[str] = Field(None, description="班次：白班/夜班")
    building: Optional[str] = Field(None, description="建筑区域")

class FireDutyScheduleItem(BaseModel):
    """值班排班记录"""
    id: str = Field(..., description="值班记录编号")
    date: str = Field(..., description="值班日期")
    shift: str = Field(..., description="班次：白班/夜班")
    staff_name: str = Field(..., description="值班人员")
    building: str = Field(..., description="值班区域")
    attendance: str = Field(..., description="出勤状态：正常/迟到/缺岗")

class FireDutyScheduleQueryResult(BaseModel):
    """值班排班查询结果"""
    total: int = Field(..., description="匹配总数")
    items: list[FireDutyScheduleItem] = Field(default_factory=list, description="值班记录列表")


# ============================================================
# 能耗监测 — fire_utility_monitor_query
# ============================================================

class FireUtilityMonitorQueryInput(BaseModel):
    """能耗监测查询请求"""
    building: Optional[str] = Field(None, description="建筑区域")
    type: Optional[str] = Field(None, description="能耗类型：electric/water")
    period: Optional[str] = Field(None, description="时间范围")
    metric: Optional[str] = Field(None, description="指标类型：有功功率/用电量/瞬时流量/累计流量/管网压力")

class FireUtilityMonitorItem(BaseModel):
    """能耗监测数据点"""
    timestamp: str = Field(..., description="时间戳")
    metric: str = Field(..., description="指标名称")
    value: float = Field(..., description="指标值")
    unit: str = Field(..., description="单位：kW/kWh/m³/h/m³/MPa")
    building: str = Field(..., description="建筑区域")

class FireUtilityMonitorQueryResult(BaseModel):
    """能耗监测查询结果"""
    total: int = Field(..., description="数据点总数")
    items: list[FireUtilityMonitorItem] = Field(default_factory=list, description="能耗数据列表")


# ============================================================
# 聚合报表 — fire_report_generate
# ============================================================

class FireReportGenerateInput(BaseModel):
    """聚合报表生成请求"""
    report_type: str = Field(..., description="报表类型：inspection/maintenance/duty/utility/alarm/overall")
    period: str = Field(..., description="时间周期：week/month/quarter/year")
    start_date: Optional[str] = Field(None, description="自定义起始日期")
    end_date: Optional[str] = Field(None, description="自定义结束日期")
    building: Optional[str] = Field(None, description="建筑区域")

class FireReportMetricItem(BaseModel):
    """报表指标项"""
    name: str = Field(..., description="指标名称")
    value: float = Field(..., description="指标值")
    unit: str = Field(..., description="单位")
    target: Optional[float] = Field(None, description="目标值")
    status: str = Field(..., description="达标状态：达标/未达标/需关注")
    change_pct: Optional[float] = Field(None, description="环比变化百分比")

class FireReportGenerateResult(BaseModel):
    """聚合报表生成结果"""
    report_type: str = Field(..., description="报表类型")
    period: str = Field(..., description="时间周期")
    metrics: list[FireReportMetricItem] = Field(default_factory=list, description="指标列表")
    generated_at: str = Field(..., description="报表生成时间")


# ============================================================
# 质量评鉴 — fire_quality_evaluate
# ============================================================

class FireQualityEvaluateInput(BaseModel):
    """质量评鉴请求"""
    modules: Optional[list[str]] = Field(None, description="评鉴模块：inspection/maintenance/duty/utility/alarm")
    period: str = Field("month", description="评鉴周期：week/month/quarter/year")
    compare_with: str = Field("last_period", description="对比方式：last_period/same_period_last_year")
    building: Optional[str] = Field(None, description="建筑区域")

class FireQualityModuleItem(BaseModel):
    """模块评鉴结果"""
    module: str = Field(..., description="模块名称")
    rating: str = Field(..., description="评级：优秀/良好/一般/较差")
    metrics: list[FireReportMetricItem] = Field(default_factory=list, description="模块指标")
    risks: Optional[list[str]] = Field(None, description="风险提示")

class FireQualityEvaluateResult(BaseModel):
    """质量评鉴结果"""
    overall_rating: str = Field(..., description="整体评级：优秀/良好/一般/较差")
    modules: list[FireQualityModuleItem] = Field(default_factory=list, description="各模块评鉴")
    suggestions: list[str] = Field(default_factory=list, description="改进建议")
    evaluated_at: str = Field(..., description="评鉴时间")


# ============================================================
# 知识检索 — graph_rag_search / knowledge_search / graph_query
# ============================================================

class KnowledgeSearchInput(BaseModel):
    """向量检索请求"""
    query: str = Field(..., description="检索问题")
    max_results: int = Field(5, description="返回结果数量上限")
    score_threshold: float = Field(0.7, description="相似度阈值")

class KnowledgeSearchResult(BaseModel):
    """向量检索结果"""
    answer: str = Field(..., description="检索到的文档片段")
    source: Optional[str] = Field(None, description="来源文件/标题")
    score: float = Field(..., description="相似度分数")

class GraphRAGSearchInput(BaseModel):
    """GraphRAG组合检索请求"""
    query: str = Field(..., description="检索问题")
    search_type: str = Field("hybrid", description="检索类型：hybrid/vector_only/graph_only")
    max_vector_results: int = Field(5, description="向量检索结果数量")
    graph_depth: int = Field(2, description="图遍历深度")
    score_threshold: float = Field(0.7, description="相似度阈值")

class GraphRAGSearchResult(BaseModel):
    """GraphRAG组合检索结果"""
    answer: str = Field(..., description="融合后的回答")
    sources: list[dict] = Field(default_factory=list, description="来源列表 [{type, source_file/title, path}]")
    score: float = Field(..., description="综合评分")
    status: str = Field("success", description="检索状态：success/low_score/fallback")

class GraphQueryInput(BaseModel):
    """图遍历查询请求"""
    entity: str = Field(..., description="起始实体名称")
    relation_types: Optional[list[str]] = Field(None, description="限定关系类型：依赖/安装于/属于分类等")
    depth: int = Field(2, description="遍历深度")
    direction: str = Field("outgoing", description="遍历方向：outgoing/incoming/both")

class GraphQueryResult(BaseModel):
    """图遍历查询结果"""
    paths: list[dict] = Field(default_factory=list, description="遍历路径 [{start, end, relation, properties}]")
    entities: list[dict] = Field(default_factory=list, description="关联实体 [{name, type, properties}]")
    total_paths: int = Field(0, description="路径总数")
