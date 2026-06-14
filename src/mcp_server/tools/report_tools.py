"""
报表评鉴 MCP 工具 — 为 fire-management-analyst 子智能体提供聚合报表和质量评鉴能力。

注册两个 MCP Tool：
    1. fire_report_generate  — 聚合报表
        Java端完成SQL聚合计算，直接返回计算好的指标（完成率/环比等），
        LLM只需解读数据和组织呈现，不参与算数。

    2. fire_quality_evaluate  — 质量评鉴
        Java端对比实际值与目标值，返回达标/异常评级。
        健康标准在Java端配置表管理，可按医院/区域/季节灵活调整。

核心设计理念：确定性计算下沉到Java后端，LLM只负责解读+建议。

Java后端接口：
    POST /reports/generate   → fire_report_generate
    POST /quality/evaluate   → fire_quality_evaluate

当前为 Mock 数据模式，待接入 Java 后端后替换为 httpx 调用。
"""

from fastmcp import FastMCP


# ============================================================
# Mock 报表数据
# ============================================================

_MOCK_REPORT_DATA = {
    "inspection": {
        "week": {"metrics": [
            {"name": "巡检完成率", "value": 92.5, "unit": "%", "target": 95.0, "status": "需关注", "change_pct": -2.1},
            {"name": "逾期率", "value": 5.3, "unit": "%", "target": 5.0, "status": "未达标", "change_pct": 0.8},
            {"name": "异常发现率", "value": 3.2, "unit": "%", "target": None, "status": "需关注", "change_pct": 1.5},
        ]},
        "month": {"metrics": [
            {"name": "巡检完成率", "value": 96.8, "unit": "%", "target": 95.0, "status": "达标", "change_pct": 1.2},
            {"name": "逾期率", "value": 3.2, "unit": "%", "target": 5.0, "status": "达标", "change_pct": -1.8},
            {"name": "异常发现率", "value": 4.5, "unit": "%", "target": None, "status": "需关注", "change_pct": 2.0},
        ]},
        "quarter": {"metrics": [
            {"name": "巡检完成率", "value": 94.5, "unit": "%", "target": 95.0, "status": "需关注", "change_pct": -0.5},
            {"name": "逾期率", "value": 4.2, "unit": "%", "target": 5.0, "status": "达标", "change_pct": -0.3},
            {"name": "异常发现率", "value": 5.1, "unit": "%", "target": None, "status": "需关注", "change_pct": 3.2},
        ]},
    },
    "maintenance": {
        "month": {"metrics": [
            {"name": "平均响应时长", "value": 18.5, "unit": "h", "target": 24.0, "status": "达标", "change_pct": -5.2},
            {"name": "完工率", "value": 92.3, "unit": "%", "target": 90.0, "status": "达标", "change_pct": 2.1},
            {"name": "工单积压数", "value": 2, "unit": "件", "target": 0, "status": "需关注", "change_pct": None},
        ]},
    },
    "duty": {
        "month": {"metrics": [
            {"name": "出勤率", "value": 98.5, "unit": "%", "target": 100.0, "status": "需关注", "change_pct": -1.5},
            {"name": "缺岗次数", "value": 1, "unit": "次", "target": 0, "status": "需关注", "change_pct": None},
        ]},
    },
    "utility": {
        "month": {"metrics": [
            {"name": "A栋月用电量", "value": 38420, "unit": "kWh", "target": None, "status": "需关注", "change_pct": 5.2},
            {"name": "B栋月用电量", "value": 28560, "unit": "kWh", "target": None, "status": "达标", "change_pct": -2.1},
            {"name": "A栋月用水量", "value": 8560, "unit": "m³", "target": None, "status": "需关注", "change_pct": 8.5},
            {"name": "B栋月用水量", "value": 5430, "unit": "m³", "target": None, "status": "达标", "change_pct": -1.3},
        ]},
    },
    "alarm": {
        "month": {"metrics": [
            {"name": "报警频次", "value": 8, "unit": "次", "target": None, "status": "需关注", "change_pct": 33.3},
            {"name": "误报率", "value": 12.5, "unit": "%", "target": 10.0, "status": "未达标", "change_pct": 5.0},
            {"name": "平均恢复时长", "value": 1.8, "unit": "h", "target": 2.0, "status": "达标", "change_pct": -0.5},
        ]},
    },
    "overall": {
        "month": {"metrics": [
            {"name": "整体健康评分", "value": 85.2, "unit": "分", "target": 90.0, "status": "需关注", "change_pct": -2.1},
            {"name": "达标模块数", "value": 3, "unit": "个", "target": 5, "status": "需关注", "change_pct": None},
            {"name": "需关注模块数", "value": 2, "unit": "个", "target": 0, "status": "未达标", "change_pct": None},
        ]},
    },
}

# ============================================================
# Mock 评鉴数据
# ============================================================

_MOCK_QUALITY_DATA = {
    "month": {
        "overall_rating": "良好",
        "modules": [
            {
                "module": "inspection",
                "rating": "良好",
                "metrics": [
                    {"name": "完成率", "value": 96.8, "unit": "%", "target": 95.0, "status": "达标", "change_pct": 1.2},
                    {"name": "逾期率", "value": 3.2, "unit": "%", "target": 5.0, "status": "达标", "change_pct": -1.8},
                ],
                "risks": ["ICU病房巡检任务逾期，需重点关注"],
            },
            {
                "module": "maintenance",
                "rating": "良好",
                "metrics": [
                    {"name": "完工率", "value": 92.3, "unit": "%", "target": 90.0, "status": "达标", "change_pct": 2.1},
                    {"name": "平均响应时长", "value": 18.5, "unit": "h", "target": 24.0, "status": "达标", "change_pct": -5.2},
                ],
                "risks": ["EPS电源故障工单待派单，需优先处理"],
            },
            {
                "module": "duty",
                "rating": "一般",
                "metrics": [
                    {"name": "出勤率", "value": 98.5, "unit": "%", "target": 100.0, "status": "需关注", "change_pct": -1.5},
                    {"name": "缺岗次数", "value": 1, "unit": "次", "target": 0, "status": "需关注", "change_pct": None},
                ],
                "risks": ["B栋夜班出现1次缺岗，建议加强排班管理"],
            },
            {
                "module": "utility",
                "rating": "一般",
                "metrics": [
                    {"name": "A栋用电环比", "value": 5.2, "unit": "%", "target": 0, "status": "需关注", "change_pct": 5.2},
                    {"name": "A栋用水环比", "value": 8.5, "unit": "%", "target": 0, "status": "未达标", "change_pct": 8.5},
                ],
                "risks": ["A栋能耗环比增长明显，建议排查是否存在设备异常或管道泄漏"],
            },
            {
                "module": "alarm",
                "rating": "较差",
                "metrics": [
                    {"name": "误报率", "value": 12.5, "unit": "%", "target": 10.0, "status": "未达标", "change_pct": 5.0},
                    {"name": "恢复时长", "value": 1.8, "unit": "h", "target": 2.0, "status": "达标", "change_pct": -0.5},
                ],
                "risks": ["误报率超标，烟感探测器可能需要重新标定或清洁"],
            },
        ],
        "suggestions": [
            "ICU病房巡检逾期需重点关注，建议增加巡检频率或安排专人跟进",
            "EPS电源故障工单待派单，建议优先分配维修人员",
            "A栋能耗环比增长明显，建议排查空调系统和大功率设备运行状态",
            "烟感探测器误报率超标，建议安排清洁标定维保",
        ],
    },
    "quarter": {
        "overall_rating": "良好",
        "modules": [
            {
                "module": "inspection",
                "rating": "良好",
                "metrics": [
                    {"name": "完成率", "value": 94.5, "unit": "%", "target": 95.0, "status": "需关注", "change_pct": -0.5},
                    {"name": "逾期率", "value": 4.2, "unit": "%", "target": 5.0, "status": "达标", "change_pct": -0.3},
                ],
                "risks": ["整体完成率略低于目标值"],
            },
            {
                "module": "maintenance",
                "rating": "优秀",
                "metrics": [
                    {"name": "完工率", "value": 95.6, "unit": "%", "target": 90.0, "status": "达标", "change_pct": 5.3},
                    {"name": "平均响应时长", "value": 16.2, "unit": "h", "target": 24.0, "status": "达标", "change_pct": -8.5},
                ],
                "risks": [],
            },
        ],
        "suggestions": [
            "巡检完成率季度均值略低于95%目标，建议下季度加强执行力度",
            "维修响应时效表现优秀，建议保持当前维修团队配置",
        ],
    },
}


def register_report_tools(mcp: FastMCP):
    """注册报表评鉴工具到 MCP Server"""

    @mcp.tool(name="fire_report_generate")
    async def fire_report_generate(
        report_type: str,
        period: str = "month",
        start_date: str | None = None,
        end_date: str | None = None,
        building: str | None = None,
    ) -> dict:
        """
        生成聚合报表。Java端完成SQL聚合计算，LLM只需解读数据和组织呈现。
        不要用明细工具做聚合计算，必须走本工具。

        Args:
            report_type: 报表类型，可选：inspection/maintenance/duty/utility/alarm/overall
            period: 时间周期，可选：week/month/quarter/year，默认 month
            start_date: 自定义起始日期（yyyy-MM-dd），覆盖 period
            end_date: 自定义结束日期（yyyy-MM-dd），覆盖 period
            building: 建筑区域过滤，如"A栋"

        Returns:
            聚合报表结果，包含 report_type、period、metrics 指标列表、generated_at
        """
        # TODO: 接入Java后端后替换为 httpx 调用
        # async with httpx.AsyncClient() as client:
        #     resp = await client.post(f"{JAVA_API_BASE_URL}/reports/generate", json={...})
        #     return resp.json()

        report_data = _MOCK_REPORT_DATA.get(report_type, {})
        period_data = report_data.get(period, {"metrics": []})

        return {
            "report_type": report_type,
            "period": period,
            "metrics": period_data["metrics"],
            "generated_at": "2026-06-14T10:00:00",
        }

    @mcp.tool(name="fire_quality_evaluate")
    async def fire_quality_evaluate(
        modules: list[str] | None = None,
        period: str = "month",
        compare_with: str = "last_period",
        building: str | None = None,
    ) -> dict:
        """
        执行质量评鉴。Java端对比实际值与目标值，返回达标/异常评级。
        LLM只需解读评鉴结果并给出改进建议。

        Args:
            modules: 评鉴模块列表，可选：inspection/maintenance/duty/utility/alarm，为空则评鉴全部
            period: 评鉴周期，可选：week/month/quarter/year，默认 month
            compare_with: 对比方式，可选：last_period(环比)/same_period_last_year(同比)，默认 last_period
            building: 建筑区域过滤

        Returns:
            评鉴结果，包含 overall_rating、各模块评鉴 modules、改进建议 suggestions、evaluated_at
        """
        # TODO: 接入Java后端后替换为 httpx 调用

        quality_data = _MOCK_QUALITY_DATA.get(period, _MOCK_QUALITY_DATA["month"])

        # 如果指定了模块，过滤返回
        filtered_modules = quality_data["modules"]
        if modules:
            filtered_modules = [m for m in filtered_modules if m["module"] in modules]

        return {
            "overall_rating": quality_data["overall_rating"],
            "modules": filtered_modules,
            "suggestions": quality_data["suggestions"],
            "evaluated_at": "2026-06-14T10:00:00",
        }
