"""
消防后勤智能助手 — MCP 工具测试 (6个明细 + 2个聚合 + 3个知识检索)

测试覆盖：
    1. fire_equipment_query — 消防设备查询
    2. fire_alarm_record_query — 火警/故障记录查询
    3. fire_inspection_query — 巡检查询
    4. fire_maintenance_order_query — 维修/维保工单查询
    5. fire_duty_schedule_query — 值班排班查询
    6. fire_utility_monitor_query — 能耗监测查询
    7. fire_report_generate — 聚合报表
    8. fire_quality_evaluate — 质量评鉴
    9. graph_rag_search — GraphRAG组合检索
    10. knowledge_search — 向量检索
    11. graph_query — 图遍历

所有测试基于 Mock 数据模式，不依赖外部服务。
"""

import pytest
import asyncio
from fastmcp import FastMCP

from mcp_server.tools.fire_equipment_tools import register_equipment_tools, _MOCK_EQUIPMENT
from mcp_server.tools.fire_alarm_tools import register_alarm_tools, _MOCK_ALARM_RECORDS
from mcp_server.tools.fire_inspection_tools import register_inspection_tools, _MOCK_INSPECTION_RECORDS
from mcp_server.tools.fire_maintenance_tools import register_maintenance_tools, _MOCK_MAINTENANCE_ORDERS
from mcp_server.tools.fire_duty_tools import register_duty_tools, _MOCK_DUTY_SCHEDULES
from mcp_server.tools.fire_utility_tools import register_utility_tools, _MOCK_UTILITY_DATA
from mcp_server.tools.report_tools import register_report_tools, _MOCK_REPORT_DATA, _MOCK_QUALITY_DATA
from mcp_server.tools.knowledge_tools import register_knowledge_tools, _MOCK_KNOWLEDGE_DOCS, _MOCK_GRAPH_PATHS


# ============================================================
# 辅助函数：创建 MCP 实例并注册工具，然后调用
# ============================================================

async def _call_tool(register_fn, tool_name: str, **kwargs) -> dict:
    """
    创建 FastMCP 实例，注册工具，然后获取工具函数并直接调用。
    """
    mcp = FastMCP("test-server")
    register_fn(mcp)

    tool = await mcp.get_tool(tool_name)
    if tool and tool.fn:
        return await tool.fn(**kwargs)
    raise KeyError(f"工具 {tool_name} 未注册")


# ============================================================
# 消防设备查询
# ============================================================

class TestFireEquipmentQuery:
    """消防设备查询工具测试"""

    @pytest.mark.asyncio
    async def test_query_all(self):
        """无过滤条件返回所有设备"""
        result = await _call_tool(register_equipment_tools, "fire_equipment_query")
        assert result["total"] == len(_MOCK_EQUIPMENT)
        assert len(result["items"]) == len(_MOCK_EQUIPMENT)

    @pytest.mark.asyncio
    async def test_query_by_name(self):
        """按名称模糊查询"""
        result = await _call_tool(register_equipment_tools, "fire_equipment_query", name="烟感")
        assert result["total"] >= 1
        for item in result["items"]:
            assert "烟感" in item["name"]

    @pytest.mark.asyncio
    async def test_query_by_location(self):
        """按位置模糊查询"""
        result = await _call_tool(register_equipment_tools, "fire_equipment_query", location="B栋")
        assert result["total"] >= 1
        for item in result["items"]:
            assert "B栋" in item["location"]

    @pytest.mark.asyncio
    async def test_query_by_category(self):
        """按分类查询"""
        result = await _call_tool(register_equipment_tools, "fire_equipment_query", category="灭火类")
        assert result["total"] >= 1
        for item in result["items"]:
            assert "灭火类" in item["category"]

    @pytest.mark.asyncio
    async def test_query_combined_filters(self):
        """多条件组合查询"""
        result = await _call_tool(
            register_equipment_tools, "fire_equipment_query",
            name="喷淋泵", location="A栋",
        )
        assert result["total"] >= 1
        for item in result["items"]:
            assert "喷淋泵" in item["name"]
            assert "A栋" in item["location"]

    @pytest.mark.asyncio
    async def test_query_no_match(self):
        """无匹配结果"""
        result = await _call_tool(register_equipment_tools, "fire_equipment_query", name="不存在的设备")
        assert result["total"] == 0
        assert result["items"] == []

    @pytest.mark.asyncio
    async def test_result_fields_complete(self):
        """返回字段完整"""
        result = await _call_tool(register_equipment_tools, "fire_equipment_query")
        if result["items"]:
            item = result["items"][0]
            required_fields = ["id", "name", "location", "category", "status"]
            for field in required_fields:
                assert field in item, f"缺少字段: {field}"


# ============================================================
# 火警/故障记录查询
# ============================================================

class TestFireAlarmRecordQuery:
    """火警/故障记录查询工具测试"""

    @pytest.mark.asyncio
    async def test_query_all(self):
        """无过滤返回所有记录"""
        result = await _call_tool(register_alarm_tools, "fire_alarm_record_query")
        assert result["total"] == len(_MOCK_ALARM_RECORDS)

    @pytest.mark.asyncio
    async def test_query_by_status(self):
        """按状态过滤"""
        result = await _call_tool(register_alarm_tools, "fire_alarm_record_query", status="待处理")
        assert result["total"] >= 1
        for item in result["items"]:
            assert item["status"] == "待处理"

    @pytest.mark.asyncio
    async def test_query_by_building(self):
        """按建筑区域过滤"""
        result = await _call_tool(register_alarm_tools, "fire_alarm_record_query", building="B栋")
        assert result["total"] >= 1
        for item in result["items"]:
            assert "B栋" in item["location"]

    @pytest.mark.asyncio
    async def test_query_by_alarm_type(self):
        """按报警类型过滤"""
        result = await _call_tool(register_alarm_tools, "fire_alarm_record_query", alarm_type="火警")
        assert result["total"] >= 1
        for item in result["items"]:
            assert item["alarm_type"] == "火警"

    @pytest.mark.asyncio
    async def test_query_by_date_range(self):
        """按日期范围过滤"""
        result = await _call_tool(
            register_alarm_tools, "fire_alarm_record_query",
            start_date="2026-06-10", end_date="2026-06-12",
        )
        assert result["total"] >= 1

    @pytest.mark.asyncio
    async def test_query_combined_filters(self):
        """多条件组合"""
        result = await _call_tool(
            register_alarm_tools, "fire_alarm_record_query",
            building="B栋", alarm_type="故障",
        )
        for item in result["items"]:
            assert "B栋" in item["location"]
            assert item["alarm_type"] == "故障"

    @pytest.mark.asyncio
    async def test_result_fields_complete(self):
        """返回字段完整"""
        result = await _call_tool(register_alarm_tools, "fire_alarm_record_query")
        if result["items"]:
            item = result["items"][0]
            required_fields = ["id", "alarm_time", "equipment_name", "alarm_type", "status", "location"]
            for field in required_fields:
                assert field in item, f"缺少字段: {field}"


# ============================================================
# 巡检查询
# ============================================================

class TestFireInspectionQuery:
    """巡检查询工具测试"""

    @pytest.mark.asyncio
    async def test_query_all(self):
        """无过滤返回所有记录"""
        result = await _call_tool(register_inspection_tools, "fire_inspection_query")
        assert result["total"] == len(_MOCK_INSPECTION_RECORDS)

    @pytest.mark.asyncio
    async def test_query_by_building(self):
        """按建筑区域过滤"""
        result = await _call_tool(register_inspection_tools, "fire_inspection_query", building="B栋")
        assert result["total"] >= 1
        for item in result["items"]:
            assert "B栋" in item["building"]

    @pytest.mark.asyncio
    async def test_query_by_status(self):
        """按状态过滤"""
        result = await _call_tool(register_inspection_tools, "fire_inspection_query", status="已完成")
        assert result["total"] >= 1
        for item in result["items"]:
            assert item["status"] == "已完成"

    @pytest.mark.asyncio
    async def test_query_overdue_tasks(self):
        """查询逾期任务"""
        result = await _call_tool(register_inspection_tools, "fire_inspection_query", status="逾期")
        assert result["total"] >= 1
        for item in result["items"]:
            assert item["status"] == "逾期"

    @pytest.mark.asyncio
    async def test_result_fields_complete(self):
        """返回字段完整"""
        result = await _call_tool(register_inspection_tools, "fire_inspection_query")
        if result["items"]:
            item = result["items"][0]
            required_fields = ["id", "task_name", "executor", "building", "status"]
            for field in required_fields:
                assert field in item, f"缺少字段: {field}"


# ============================================================
# 维修/维保工单查询
# ============================================================

class TestFireMaintenanceOrderQuery:
    """维修/维保工单查询工具测试"""

    @pytest.mark.asyncio
    async def test_query_all(self):
        """无过滤返回所有工单"""
        result = await _call_tool(register_maintenance_tools, "fire_maintenance_order_query")
        assert result["total"] == len(_MOCK_MAINTENANCE_ORDERS)

    @pytest.mark.asyncio
    async def test_query_by_order_id(self):
        """按工单号精确查询"""
        result = await _call_tool(
            register_maintenance_tools, "fire_maintenance_order_query",
            order_id="MO-202606-001",
        )
        assert result["total"] == 1
        assert result["items"][0]["order_id"] == "MO-202606-001"

    @pytest.mark.asyncio
    async def test_query_by_status(self):
        """按状态过滤"""
        result = await _call_tool(
            register_maintenance_tools, "fire_maintenance_order_query",
            status="维修中",
        )
        assert result["total"] >= 1
        for item in result["items"]:
            assert item["status"] == "维修中"

    @pytest.mark.asyncio
    async def test_query_by_type(self):
        """按类型过滤（维修/维保）"""
        result = await _call_tool(
            register_maintenance_tools, "fire_maintenance_order_query",
            type="维保",
        )
        assert result["total"] >= 1
        for item in result["items"]:
            assert item["type"] == "维保"

    @pytest.mark.asyncio
    async def test_query_by_building(self):
        """按建筑区域过滤"""
        result = await _call_tool(
            register_maintenance_tools, "fire_maintenance_order_query",
            building="A栋",
        )
        assert result["total"] >= 1

    @pytest.mark.asyncio
    async def test_query_no_match_order_id(self):
        """不存在的工单号返回空"""
        result = await _call_tool(
            register_maintenance_tools, "fire_maintenance_order_query",
            order_id="MO-NONEXIST",
        )
        assert result["total"] == 0


# ============================================================
# 值班排班查询
# ============================================================

class TestFireDutyScheduleQuery:
    """值班排班查询工具测试"""

    @pytest.mark.asyncio
    async def test_query_all(self):
        """无过滤返回所有排班"""
        result = await _call_tool(register_duty_tools, "fire_duty_schedule_query")
        assert result["total"] == len(_MOCK_DUTY_SCHEDULES)

    @pytest.mark.asyncio
    async def test_query_by_date(self):
        """按日期查询"""
        result = await _call_tool(
            register_duty_tools, "fire_duty_schedule_query",
            date="2026-06-12",
        )
        assert result["total"] >= 1
        for item in result["items"]:
            assert item["date"] == "2026-06-12"

    @pytest.mark.asyncio
    async def test_query_by_shift(self):
        """按班次查询"""
        result = await _call_tool(
            register_duty_tools, "fire_duty_schedule_query",
            shift="夜班",
        )
        assert result["total"] >= 1
        for item in result["items"]:
            assert item["shift"] == "夜班"

    @pytest.mark.asyncio
    async def test_query_by_building(self):
        """按建筑区域查询"""
        result = await _call_tool(
            register_duty_tools, "fire_duty_schedule_query",
            building="A栋",
        )
        assert result["total"] >= 1

    @pytest.mark.asyncio
    async def test_query_absent_record(self):
        """查询缺岗记录"""
        result = await _call_tool(
            register_duty_tools, "fire_duty_schedule_query",
            date="2026-06-09",
        )
        # 检查是否有缺岗记录
        absent = [i for i in result["items"] if i["attendance"] == "缺岗"]
        assert len(absent) >= 1


# ============================================================
# 能耗监测查询
# ============================================================

class TestFireUtilityMonitorQuery:
    """能耗监测查询工具测试"""

    @pytest.mark.asyncio
    async def test_query_all(self):
        """无过滤返回所有数据"""
        result = await _call_tool(register_utility_tools, "fire_utility_monitor_query")
        assert result["total"] == len(_MOCK_UTILITY_DATA)

    @pytest.mark.asyncio
    async def test_query_by_building(self):
        """按建筑区域过滤"""
        result = await _call_tool(
            register_utility_tools, "fire_utility_monitor_query",
            building="A栋",
        )
        assert result["total"] >= 1
        for item in result["items"]:
            assert "A栋" in item["building"]

    @pytest.mark.asyncio
    async def test_query_electric(self):
        """查询电能数据"""
        result = await _call_tool(
            register_utility_tools, "fire_utility_monitor_query",
            type="electric",
        )
        assert result["total"] >= 1
        for item in result["items"]:
            assert item["type"] == "electric"

    @pytest.mark.asyncio
    async def test_query_water(self):
        """查询水能数据"""
        result = await _call_tool(
            register_utility_tools, "fire_utility_monitor_query",
            type="water",
        )
        assert result["total"] >= 1
        for item in result["items"]:
            assert item["type"] == "water"

    @pytest.mark.asyncio
    async def test_query_by_metric(self):
        """按指标类型过滤"""
        result = await _call_tool(
            register_utility_tools, "fire_utility_monitor_query",
            metric="有功功率",
        )
        assert result["total"] >= 1
        for item in result["items"]:
            assert "有功功率" in item["metric"]

    @pytest.mark.asyncio
    async def test_result_fields_complete(self):
        """返回字段完整"""
        result = await _call_tool(register_utility_tools, "fire_utility_monitor_query")
        if result["items"]:
            item = result["items"][0]
            required_fields = ["timestamp", "metric", "value", "unit", "building"]
            for field in required_fields:
                assert field in item, f"缺少字段: {field}"


# ============================================================
# 聚合报表
# ============================================================

class TestFireReportGenerate:
    """聚合报表工具测试"""

    @pytest.mark.asyncio
    async def test_inspection_month_report(self):
        """巡检月报"""
        result = await _call_tool(
            register_report_tools, "fire_report_generate",
            report_type="inspection", period="month",
        )
        assert result["report_type"] == "inspection"
        assert result["period"] == "month"
        assert len(result["metrics"]) > 0
        assert "generated_at" in result

    @pytest.mark.asyncio
    async def test_overall_month_report(self):
        """综合月报"""
        result = await _call_tool(
            register_report_tools, "fire_report_generate",
            report_type="overall", period="month",
        )
        assert result["report_type"] == "overall"
        assert len(result["metrics"]) > 0

    @pytest.mark.asyncio
    async def test_maintenance_report(self):
        """维修报表"""
        result = await _call_tool(
            register_report_tools, "fire_report_generate",
            report_type="maintenance", period="month",
        )
        assert result["report_type"] == "maintenance"

    @pytest.mark.asyncio
    async def test_alarm_report(self):
        """火警报表"""
        result = await _call_tool(
            register_report_tools, "fire_report_generate",
            report_type="alarm", period="month",
        )
        assert result["report_type"] == "alarm"
        # 确认火警报表包含误报率等关键指标
        metric_names = [m["name"] for m in result["metrics"]]
        assert "误报率" in metric_names

    @pytest.mark.asyncio
    async def test_duty_report(self):
        """值班报表"""
        result = await _call_tool(
            register_report_tools, "fire_report_generate",
            report_type="duty", period="month",
        )
        assert result["report_type"] == "duty"

    @pytest.mark.asyncio
    async def test_utility_report(self):
        """能耗报表"""
        result = await _call_tool(
            register_report_tools, "fire_report_generate",
            report_type="utility", period="month",
        )
        assert result["report_type"] == "utility"

    @pytest.mark.asyncio
    async def test_inspection_quarter_report(self):
        """巡检季报"""
        result = await _call_tool(
            register_report_tools, "fire_report_generate",
            report_type="inspection", period="quarter",
        )
        assert result["period"] == "quarter"
        assert len(result["metrics"]) > 0

    @pytest.mark.asyncio
    async def test_metric_fields_complete(self):
        """指标项字段完整"""
        result = await _call_tool(
            register_report_tools, "fire_report_generate",
            report_type="inspection", period="month",
        )
        for metric in result["metrics"]:
            required_fields = ["name", "value", "unit", "status"]
            for field in required_fields:
                assert field in metric, f"指标缺少字段: {field}"

    @pytest.mark.asyncio
    async def test_report_type_not_in_mock(self):
        """请求不存在的报表类型（Mock中无数据）"""
        result = await _call_tool(
            register_report_tools, "fire_report_generate",
            report_type="nonexistent", period="month",
        )
        assert result["report_type"] == "nonexistent"
        assert result["metrics"] == []

    @pytest.mark.asyncio
    async def test_period_not_in_mock(self):
        """请求不存在的周期（Mock中无数据）"""
        result = await _call_tool(
            register_report_tools, "fire_report_generate",
            report_type="inspection", period="year",
        )
        assert result["period"] == "year"
        # 无对应周期数据时返回空指标
        assert result["metrics"] == []


# ============================================================
# 质量评鉴
# ============================================================

class TestFireQualityEvaluate:
    """质量评鉴工具测试"""

    @pytest.mark.asyncio
    async def test_evaluate_all_modules_month(self):
        """月度全模块评鉴"""
        result = await _call_tool(
            register_report_tools, "fire_quality_evaluate",
            period="month",
        )
        assert result["overall_rating"] in ["优秀", "良好", "一般", "较差"]
        assert len(result["modules"]) > 0
        assert len(result["suggestions"]) > 0
        assert "evaluated_at" in result

    @pytest.mark.asyncio
    async def test_evaluate_specific_module(self):
        """评鉴指定模块"""
        result = await _call_tool(
            register_report_tools, "fire_quality_evaluate",
            modules=["inspection"], period="month",
        )
        assert len(result["modules"]) == 1
        assert result["modules"][0]["module"] == "inspection"

    @pytest.mark.asyncio
    async def test_evaluate_multiple_modules(self):
        """评鉴多个模块"""
        result = await _call_tool(
            register_report_tools, "fire_quality_evaluate",
            modules=["inspection", "alarm"], period="month",
        )
        module_names = [m["module"] for m in result["modules"]]
        assert "inspection" in module_names
        assert "alarm" in module_names

    @pytest.mark.asyncio
    async def test_evaluate_quarter(self):
        """季度评鉴"""
        result = await _call_tool(
            register_report_tools, "fire_quality_evaluate",
            period="quarter",
        )
        assert "overall_rating" in result

    @pytest.mark.asyncio
    async def test_module_rating_values(self):
        """模块评级枚举值正确"""
        result = await _call_tool(
            register_report_tools, "fire_quality_evaluate",
            period="month",
        )
        valid_ratings = {"优秀", "良好", "一般", "较差"}
        for module in result["modules"]:
            assert module["rating"] in valid_ratings

    @pytest.mark.asyncio
    async def test_module_has_risks(self):
        """评鉴结果包含风险提示"""
        result = await _call_tool(
            register_report_tools, "fire_quality_evaluate",
            period="month",
        )
        # 至少一个模块有风险提示
        has_risks = any(m.get("risks") and len(m["risks"]) > 0 for m in result["modules"])
        assert has_risks, "月度评鉴应至少有一个模块存在风险"

    @pytest.mark.asyncio
    async def test_module_has_suggestions(self):
        """评鉴结果包含改进建议"""
        result = await _call_tool(
            register_report_tools, "fire_quality_evaluate",
            period="month",
        )
        assert len(result["suggestions"]) > 0

    @pytest.mark.asyncio
    async def test_evaluate_nonexistent_module(self):
        """评鉴不存在的模块返回空列表"""
        result = await _call_tool(
            register_report_tools, "fire_quality_evaluate",
            modules=["nonexistent"], period="month",
        )
        assert result["modules"] == []


# ============================================================
# 知识检索 — graph_rag_search
# ============================================================

class TestGraphRAGSearch:
    """GraphRAG组合检索工具测试"""

    @pytest.mark.asyncio
    async def test_search_icu_query(self):
        """ICU病房相关查询"""
        result = await _call_tool(
            register_knowledge_tools, "graph_rag_search",
            query="ICU病房消防系统要求",
        )
        assert result["answer"] != ""
        assert result["score"] > 0
        assert result["status"] in ["success", "low_score", "fallback"]
        assert len(result["sources"]) > 0

    @pytest.mark.asyncio
    async def test_search_with_low_threshold(self):
        """低阈值应返回结果"""
        result = await _call_tool(
            register_knowledge_tools, "graph_rag_search",
            query="测试查询", score_threshold=0.5,
        )
        assert result["score"] >= 0.5 or result["status"] == "success"

    @pytest.mark.asyncio
    async def test_search_returns_sources(self):
        """结果包含来源信息"""
        result = await _call_tool(
            register_knowledge_tools, "graph_rag_search",
            query="灭火器类型",
        )
        assert "sources" in result
        if result["sources"]:
            source = result["sources"][0]
            assert "type" in source
            assert "title" in source

    @pytest.mark.asyncio
    async def test_search_no_match_returns_fallback(self):
        """无匹配时返回最高分文档作为兜底"""
        result = await _call_tool(
            register_knowledge_tools, "graph_rag_search",
            query="完全不相关的查询xyz",
        )
        # Mock 模式下会返回最高分文档
        assert result["answer"] != ""


# ============================================================
# 知识检索 — knowledge_search
# ============================================================

class TestKnowledgeSearch:
    """向量检索工具测试"""

    @pytest.mark.asyncio
    async def test_search_returns_results(self):
        """检索返回结果"""
        result = await _call_tool(
            register_knowledge_tools, "knowledge_search",
            query="ICU病房消防",
        )
        assert "total" in result
        assert "items" in result

    @pytest.mark.asyncio
    async def test_search_max_results(self):
        """限制返回数量"""
        result = await _call_tool(
            register_knowledge_tools, "knowledge_search",
            query="消防", max_results=2,
        )
        assert result["total"] <= 2

    @pytest.mark.asyncio
    async def test_search_no_match_returns_fallback(self):
        """无匹配时返回最高分文档"""
        result = await _call_tool(
            register_knowledge_tools, "knowledge_search",
            query="xyz不相关查询",
        )
        # Mock 模式下会返回最高分文档
        assert result["total"] >= 1

    @pytest.mark.asyncio
    async def test_search_item_fields(self):
        """检索结果字段完整"""
        result = await _call_tool(
            register_knowledge_tools, "knowledge_search",
            query="灭火器",
        )
        if result["items"]:
            item = result["items"][0]
            assert "answer" in item
            assert "source" in item
            assert "score" in item


# ============================================================
# 知识检索 — graph_query
# ============================================================

class TestGraphQuery:
    """图遍历查询工具测试"""

    @pytest.mark.asyncio
    async def test_query_eps_power(self):
        """查询EPS电源依赖关系"""
        result = await _call_tool(
            register_knowledge_tools, "graph_query",
            entity="EPS电源-01",
        )
        assert len(result["paths"]) > 0
        assert len(result["entities"]) > 0
        assert result["total_paths"] > 0

    @pytest.mark.asyncio
    async def test_query_icu_ward(self):
        """查询ICU病房关联关系"""
        result = await _call_tool(
            register_knowledge_tools, "graph_query",
            entity="ICU病房",
        )
        assert len(result["paths"]) > 0
        # ICU病房应关联到一类重点场所和法规
        entity_names = [e["name"] for e in result["entities"]]
        assert "一类重点场所" in entity_names

    @pytest.mark.asyncio
    async def test_query_with_relation_filter(self):
        """按关系类型过滤"""
        result = await _call_tool(
            register_knowledge_tools, "graph_query",
            entity="EPS电源-01", relation_types=["供电给"],
        )
        for path in result["paths"]:
            assert path["relation"] == "供电给"

    @pytest.mark.asyncio
    async def test_query_unknown_entity(self):
        """查询不存在的实体返回空结果"""
        result = await _call_tool(
            register_knowledge_tools, "graph_query",
            entity="不存在的设备-999",
        )
        assert result["paths"] == []
        assert result["entities"] == []
        assert result["total_paths"] == 0

    @pytest.mark.asyncio
    async def test_query_path_fields(self):
        """路径字段完整"""
        result = await _call_tool(
            register_knowledge_tools, "graph_query",
            entity="EPS电源-01",
        )
        if result["paths"]:
            path = result["paths"][0]
            assert "start" in path
            assert "end" in path
            assert "relation" in path

    @pytest.mark.asyncio
    async def test_query_entity_fields(self):
        """实体字段完整"""
        result = await _call_tool(
            register_knowledge_tools, "graph_query",
            entity="EPS电源-01",
        )
        if result["entities"]:
            entity = result["entities"][0]
            assert "name" in entity
            assert "type" in entity
            assert "properties" in entity

    @pytest.mark.asyncio
    async def test_query_with_depth_limit(self):
        """深度限制"""
        result = await _call_tool(
            register_knowledge_tools, "graph_query",
            entity="EPS电源-01", depth=1,
        )
        # depth=1 时路径数量应受限
        assert result["total_paths"] > 0

    @pytest.mark.asyncio
    async def test_eps_power_dependents(self):
        """EPS电源故障影响链 — 验证Mock数据完整性"""
        result = await _call_tool(
            register_knowledge_tools, "graph_query",
            entity="EPS电源-01",
        )
        # EPS电源应供电给喷淋泵和排烟风机
        end_entities = [p["end"] for p in result["paths"]]
        assert "喷淋泵-01" in end_entities
        assert "排烟风机-02" in end_entities
