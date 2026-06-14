"""
消防后勤智能助手 — MCP 工具数据模型测试 (mcp_tools_bean.py)

测试覆盖：
    1. 分组名称常量
    2. 设备查询模型 (FireEquipmentQueryInput/Item/Result)
    3. 火警/故障记录模型
    4. 巡检查询模型
    5. 维修/维保工单模型
    6. 值班排班模型
    7. 能耗监测模型
    8. 聚合报表模型
    9. 质量评鉴模型
    10. 知识检索模型
"""

import pytest

from agent.mcp_tools_bean import (
    # 分组常量
    GROUP_FIRE_EQUIPMENT,
    GROUP_FIRE_ALARM,
    GROUP_FIRE_INSPECTION,
    GROUP_FIRE_MAINTENANCE,
    GROUP_FIRE_DUTY,
    GROUP_FIRE_UTILITY,
    GROUP_KNOWLEDGE,
    GROUP_REPORT,
    # 设备
    FireEquipmentQueryInput,
    FireEquipmentItem,
    FireEquipmentQueryResult,
    # 火警
    FireAlarmRecordQueryInput,
    FireAlarmRecordItem,
    FireAlarmRecordQueryResult,
    # 巡检
    FireInspectionQueryInput,
    FireInspectionItem,
    FireInspectionQueryResult,
    # 维修
    FireMaintenanceOrderQueryInput,
    FireMaintenanceOrderItem,
    FireMaintenanceOrderQueryResult,
    # 值班
    FireDutyScheduleQueryInput,
    FireDutyScheduleItem,
    FireDutyScheduleQueryResult,
    # 能耗
    FireUtilityMonitorQueryInput,
    FireUtilityMonitorItem,
    FireUtilityMonitorQueryResult,
    # 报表
    FireReportGenerateInput,
    FireReportMetricItem,
    FireReportGenerateResult,
    # 评鉴
    FireQualityEvaluateInput,
    FireQualityModuleItem,
    FireQualityEvaluateResult,
    # 知识检索
    KnowledgeSearchInput,
    KnowledgeSearchResult,
    GraphRAGSearchInput,
    GraphRAGSearchResult,
    GraphQueryInput,
    GraphQueryResult,
)


# ============================================================
# 分组名称常量
# ============================================================

class TestGroupConstants:
    """分组常量测试 — 确认值符合命名约定"""

    def test_group_values(self):
        """所有分组常量值正确"""
        assert GROUP_FIRE_EQUIPMENT == "fire_equipment"
        assert GROUP_FIRE_ALARM == "fire_alarm"
        assert GROUP_FIRE_INSPECTION == "fire_inspection"
        assert GROUP_FIRE_MAINTENANCE == "fire_maintenance"
        assert GROUP_FIRE_DUTY == "fire_duty"
        assert GROUP_FIRE_UTILITY == "fire_utility"
        assert GROUP_KNOWLEDGE == "knowledge"
        assert GROUP_REPORT == "report"

    def test_group_count(self):
        """共8个分组"""
        groups = [
            GROUP_FIRE_EQUIPMENT, GROUP_FIRE_ALARM, GROUP_FIRE_INSPECTION,
            GROUP_FIRE_MAINTENANCE, GROUP_FIRE_DUTY, GROUP_FIRE_UTILITY,
            GROUP_KNOWLEDGE, GROUP_REPORT,
        ]
        assert len(groups) == 8
        assert len(set(groups)) == 8  # 无重复


# ============================================================
# 设备查询
# ============================================================

class TestFireEquipmentModels:
    """消防设备查询模型测试"""

    def test_query_input_all_optional(self):
        """查询输入所有字段可选"""
        inp = FireEquipmentQueryInput()
        assert inp.name is None
        assert inp.location is None
        assert inp.category is None

    def test_query_input_with_filters(self):
        """带过滤条件的查询输入"""
        inp = FireEquipmentQueryInput(
            name="烟感",
            location="B栋3层",
            category="火灾探测类",
        )
        assert inp.name == "烟感"
        assert inp.location == "B栋3层"
        assert inp.category == "火灾探测类"

    def test_equipment_item(self):
        """设备信息项"""
        item = FireEquipmentItem(
            id="EQ-001",
            name="烟感探测器-01",
            location="B栋3层",
            category="火灾探测类",
            status="正常",
            install_date="2024-03-15",
            last_check_date="2026-05-20",
        )
        assert item.id == "EQ-001"
        assert item.status == "正常"

    def test_equipment_item_optional_dates(self):
        """设备信息项日期可选"""
        item = FireEquipmentItem(
            id="EQ-001", name="烟感探测器-01",
            location="B栋3层", category="火灾探测类", status="正常",
        )
        assert item.install_date is None
        assert item.last_check_date is None

    def test_query_result(self):
        """设备查询结果"""
        items = [
            FireEquipmentItem(
                id="EQ-001", name="烟感探测器-01",
                location="B栋3层", category="火灾探测类", status="正常",
            ),
        ]
        result = FireEquipmentQueryResult(total=1, items=items)
        assert result.total == 1
        assert len(result.items) == 1

    def test_query_result_empty(self):
        """空查询结果"""
        result = FireEquipmentQueryResult(total=0)
        assert result.items == []


# ============================================================
# 火警/故障记录
# ============================================================

class TestFireAlarmModels:
    """火警/故障记录模型测试"""

    def test_query_input_all_optional(self):
        """所有过滤条件可选"""
        inp = FireAlarmRecordQueryInput()
        assert inp.start_date is None
        assert inp.end_date is None
        assert inp.status is None
        assert inp.building is None
        assert inp.alarm_type is None

    def test_query_input_with_filters(self):
        """带过滤条件的查询"""
        inp = FireAlarmRecordQueryInput(
            start_date="2026-06-01",
            end_date="2026-06-14",
            status="待处理",
            building="B栋",
            alarm_type="火警",
        )
        assert inp.start_date == "2026-06-01"
        assert inp.alarm_type == "火警"

    def test_alarm_record_item(self):
        """报警记录项"""
        item = FireAlarmRecordItem(
            id="ALM-001",
            alarm_time="2026-06-12 08:23:45",
            equipment_name="烟感探测器-01",
            alarm_type="火警",
            status="已恢复",
            location="B栋3层",
        )
        assert item.id == "ALM-001"
        assert item.alarm_type == "火警"

    def test_alarm_record_item_optional_fields(self):
        """报警记录可选项"""
        item = FireAlarmRecordItem(
            id="ALM-005",
            alarm_time="2026-06-08 10:12:55",
            equipment_name="EPS电源-01",
            alarm_type="故障",
            status="待处理",
            location="A栋配电间",
        )
        assert item.handler is None
        assert item.recover_time is None

    def test_query_result(self):
        """查询结果"""
        result = FireAlarmRecordQueryResult(total=3, items=[])
        assert result.total == 3


# ============================================================
# 巡检查询
# ============================================================

class TestFireInspectionModels:
    """巡检查询模型测试"""

    def test_query_input(self):
        """巡检查询输入"""
        inp = FireInspectionQueryInput(building="B栋3层", status="已完成")
        assert inp.building == "B栋3层"
        assert inp.status == "已完成"

    def test_inspection_item(self):
        """巡检记录项"""
        item = FireInspectionItem(
            id="INS-001",
            task_name="B栋3层消防设施日常巡检",
            executor="张伟",
            building="B栋3层",
            status="已完成",
            completed_at="2026-06-12 10:30:00",
            check_items_count=15,
            abnormal_count=0,
        )
        assert item.abnormal_count == 0

    def test_inspection_item_defaults(self):
        """巡检记录默认值"""
        item = FireInspectionItem(
            id="INS-005",
            task_name="A栋2层消火栓系统巡检",
            executor="陈明",
            building="A栋2层",
            status="待执行",
        )
        assert item.check_items_count == 0
        assert item.abnormal_count == 0
        assert item.completed_at is None


# ============================================================
# 维修/维保工单
# ============================================================

class TestFireMaintenanceModels:
    """维修/维保工单模型测试"""

    def test_query_input(self):
        """工单查询输入"""
        inp = FireMaintenanceOrderQueryInput(order_id="MO-202606-001", status="维修中")
        assert inp.order_id == "MO-202606-001"

    def test_maintenance_order_item(self):
        """工单信息项"""
        item = FireMaintenanceOrderItem(
            order_id="MO-202606-001",
            type="维修",
            equipment_name="排烟风机-02",
            status="维修中",
            building="B栋4层",
        )
        assert item.type == "维修"
        assert item.dispatcher is None

    def test_maintenance_order_status_flow(self):
        """工单状态流转字段"""
        # 验证所有状态值可正常赋值
        for status in ["待派单", "已派单", "维修中", "已完成", "已验收", "已取消"]:
            item = FireMaintenanceOrderItem(
                order_id="MO-001", type="维修",
                equipment_name="设备", status=status, building="A栋",
            )
            assert item.status == status


# ============================================================
# 值班排班
# ============================================================

class TestFireDutyModels:
    """值班排班模型测试"""

    def test_query_input(self):
        """值班查询输入"""
        inp = FireDutyScheduleQueryInput(date="2026-06-12", shift="白班")
        assert inp.date == "2026-06-12"
        assert inp.shift == "白班"

    def test_duty_schedule_item(self):
        """值班记录项"""
        item = FireDutyScheduleItem(
            id="DUT-001",
            date="2026-06-12",
            shift="白班",
            staff_name="张伟",
            building="A栋",
            attendance="正常",
        )
        assert item.attendance == "正常"

    def test_attendance_values(self):
        """出勤状态枚举值"""
        for val in ["正常", "迟到", "缺岗"]:
            item = FireDutyScheduleItem(
                id="DUT-001", date="2026-06-12", shift="白班",
                staff_name="张伟", building="A栋", attendance=val,
            )
            assert item.attendance == val


# ============================================================
# 能耗监测
# ============================================================

class TestFireUtilityModels:
    """能耗监测模型测试"""

    def test_query_input(self):
        """能耗查询输入"""
        inp = FireUtilityMonitorQueryInput(building="A栋", type="electric")
        assert inp.type == "electric"

    def test_utility_item(self):
        """能耗数据项"""
        item = FireUtilityMonitorItem(
            timestamp="2026-06-12 08:00",
            metric="有功功率",
            value=125.5,
            unit="kW",
            building="A栋",
        )
        assert item.value == 125.5
        assert item.unit == "kW"

    def test_utility_types(self):
        """能耗类型枚举"""
        for type_val in ["electric", "water"]:
            inp = FireUtilityMonitorQueryInput(type=type_val)
            assert inp.type == type_val

    def test_utility_metrics(self):
        """能耗指标枚举"""
        metrics = ["有功功率", "用电量", "瞬时流量", "累计流量", "管网压力"]
        for metric in metrics:
            item = FireUtilityMonitorItem(
                timestamp="2026-06-12 08:00",
                metric=metric, value=100.0, unit="kW", building="A栋",
            )
            assert item.metric == metric


# ============================================================
# 聚合报表
# ============================================================

class TestFireReportModels:
    """聚合报表模型测试"""

    def test_report_input_required(self):
        """报表请求必填字段"""
        inp = FireReportGenerateInput(report_type="inspection", period="month")
        assert inp.report_type == "inspection"
        assert inp.period == "month"

    def test_report_input_optional(self):
        """报表请求可选字段"""
        inp = FireReportGenerateInput(
            report_type="overall",
            period="quarter",
            start_date="2026-04-01",
            end_date="2026-06-30",
            building="A栋",
        )
        assert inp.start_date == "2026-04-01"

    def test_report_types(self):
        """报表类型枚举"""
        for rt in ["inspection", "maintenance", "duty", "utility", "alarm", "overall"]:
            inp = FireReportGenerateInput(report_type=rt, period="month")
            assert inp.report_type == rt

    def test_metric_item(self):
        """指标项"""
        item = FireReportMetricItem(
            name="巡检完成率",
            value=96.8,
            unit="%",
            target=95.0,
            status="达标",
            change_pct=1.2,
        )
        assert item.status == "达标"
        assert item.change_pct == 1.2

    def test_metric_item_optional_target(self):
        """指标项目标值可选"""
        item = FireReportMetricItem(
            name="异常发现率", value=4.5, unit="%", status="需关注",
        )
        assert item.target is None
        assert item.change_pct is None

    def test_report_result(self):
        """报表结果"""
        result = FireReportGenerateResult(
            report_type="inspection",
            period="month",
            metrics=[],
            generated_at="2026-06-14T10:00:00",
        )
        assert result.report_type == "inspection"


# ============================================================
# 质量评鉴
# ============================================================

class TestFireQualityModels:
    """质量评鉴模型测试"""

    def test_evaluate_input_defaults(self):
        """评鉴请求默认值"""
        inp = FireQualityEvaluateInput()
        assert inp.period == "month"
        assert inp.compare_with == "last_period"
        assert inp.modules is None
        assert inp.building is None

    def test_evaluate_input_with_modules(self):
        """指定评鉴模块"""
        inp = FireQualityEvaluateInput(modules=["inspection", "alarm"])
        assert len(inp.modules) == 2

    def test_module_item(self):
        """模块评鉴结果"""
        item = FireQualityModuleItem(
            module="inspection",
            rating="良好",
            metrics=[],
            risks=["ICU病房巡检逾期"],
        )
        assert item.rating == "良好"
        assert len(item.risks) == 1

    def test_evaluate_result(self):
        """评鉴结果"""
        result = FireQualityEvaluateResult(
            overall_rating="良好",
            modules=[],
            suggestions=["加强巡检执行力度"],
            evaluated_at="2026-06-14T10:00:00",
        )
        assert result.overall_rating == "良好"
        assert len(result.suggestions) == 1


# ============================================================
# 知识检索
# ============================================================

class TestKnowledgeModels:
    """知识检索模型测试"""

    def test_knowledge_search_input(self):
        """向量检索请求"""
        inp = KnowledgeSearchInput(query="ICU病房消防系统要求")
        assert inp.query == "ICU病房消防系统要求"
        assert inp.max_results == 5
        assert inp.score_threshold == 0.7

    def test_knowledge_search_result(self):
        """向量检索结果"""
        result = KnowledgeSearchResult(
            answer="ICU病房属于一类重点场所...",
            source="GB 50974-2014",
            score=0.92,
        )
        assert result.score == 0.92

    def test_graph_rag_search_input(self):
        """GraphRAG组合检索请求"""
        inp = GraphRAGSearchInput(query="灭火器类型")
        assert inp.search_type == "hybrid"
        assert inp.max_vector_results == 5
        assert inp.graph_depth == 2

    def test_graph_rag_search_input_custom(self):
        """GraphRAG自定义参数"""
        inp = GraphRAGSearchInput(
            query="测试",
            search_type="vector_only",
            max_vector_results=10,
            graph_depth=3,
        )
        assert inp.search_type == "vector_only"

    def test_graph_rag_search_result(self):
        """GraphRAG组合检索结果"""
        result = GraphRAGSearchResult(
            answer="回答内容",
            sources=[{"type": "document", "title": "法规", "path": ""}],
            score=0.85,
            status="success",
        )
        assert result.status == "success"
        assert len(result.sources) == 1

    def test_graph_query_input(self):
        """图遍历请求"""
        inp = GraphQueryInput(entity="EPS电源-01")
        assert inp.entity == "EPS电源-01"
        assert inp.relation_types is None
        assert inp.depth == 2
        assert inp.direction == "outgoing"

    def test_graph_query_input_with_filters(self):
        """图遍历请求带关系过滤"""
        inp = GraphQueryInput(
            entity="EPS电源-01",
            relation_types=["供电给", "控制"],
            depth=3,
            direction="both",
        )
        assert len(inp.relation_types) == 2
        assert inp.direction == "both"

    def test_graph_query_result(self):
        """图遍历结果"""
        result = GraphQueryResult(
            paths=[{"start": "A", "end": "B", "relation": "依赖", "properties": {}}],
            entities=[{"name": "A", "type": "Equipment", "properties": {}}],
            total_paths=1,
        )
        assert result.total_paths == 1

    def test_graph_query_result_empty(self):
        """空图遍历结果"""
        result = GraphQueryResult()
        assert result.paths == []
        assert result.entities == []
        assert result.total_paths == 0
