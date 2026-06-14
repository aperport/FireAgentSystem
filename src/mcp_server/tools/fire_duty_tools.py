"""
消防值班排班查询 MCP 工具 — 查询值班排班与值班记录。

注册 MCP Tool：
    fire_duty_schedule_query — 查询值班排班和值班记录

查询参数：
    - date：查询日期（yyyy-MM-dd）
    - shift：班次（白班/夜班）
    - building：建筑区域过滤

返回：值班日期、班次、值班人员、出勤状态等。

Java后端接口：GET /duty/schedules

注意：聚合统计（出勤率/缺岗次数）应走 fire_report_generate，
本工具仅查明细记录，不应被用来做聚合计算。

当前为 Mock 数据模式，待接入 Java 后端后替换为 httpx 调用。
"""

from fastmcp import FastMCP


# ============================================================
# Mock 数据
# ============================================================

_MOCK_DUTY_SCHEDULES = [
    {"id": "DUT-001", "date": "2026-06-12", "shift": "白班", "staff_name": "张伟", "building": "A栋", "attendance": "正常"},
    {"id": "DUT-002", "date": "2026-06-12", "shift": "夜班", "staff_name": "李强", "building": "B栋", "attendance": "正常"},
    {"id": "DUT-003", "date": "2026-06-11", "shift": "白班", "staff_name": "王芳", "building": "A栋", "attendance": "正常"},
    {"id": "DUT-004", "date": "2026-06-11", "shift": "夜班", "staff_name": "赵军", "building": "B栋", "attendance": "迟到"},
    {"id": "DUT-005", "date": "2026-06-10", "shift": "白班", "staff_name": "陈明", "building": "C栋", "attendance": "正常"},
    {"id": "DUT-006", "date": "2026-06-10", "shift": "夜班", "staff_name": "张伟", "building": "A栋", "attendance": "正常"},
    {"id": "DUT-007", "date": "2026-06-09", "shift": "白班", "staff_name": "李强", "building": "B栋", "attendance": "缺岗"},
    {"id": "DUT-008", "date": "2026-06-09", "shift": "夜班", "staff_name": "王芳", "building": "A栋", "attendance": "正常"},
    {"id": "DUT-009", "date": "2026-06-08", "shift": "白班", "staff_name": "赵军", "building": "C栋", "attendance": "正常"},
    {"id": "DUT-010", "date": "2026-06-08", "shift": "夜班", "staff_name": "陈明", "building": "B栋", "attendance": "正常"},
]


def register_duty_tools(mcp: FastMCP):
    """注册值班排班查询工具到 MCP Server"""

    @mcp.tool(name="fire_duty_schedule_query")
    async def fire_duty_schedule_query(
        date: str | None = None,
        shift: str | None = None,
        building: str | None = None,
    ) -> dict:
        """
        查询值班排班和值班记录。支持按日期、班次、区域过滤。
        不要用于聚合统计（出勤率/缺岗次数），聚合统计应走 fire_report_generate。

        Args:
            date: 查询日期（yyyy-MM-dd），如"2026-06-12"
            shift: 班次，可选：白班/夜班
            building: 建筑区域过滤，如"A栋"、"B栋"

        Returns:
            值班记录查询结果，包含 total 和 items 列表
        """
        # TODO: 接入Java后端后替换为 httpx 调用

        results = list(_MOCK_DUTY_SCHEDULES)

        if date:
            results = [r for r in results if r["date"] == date]
        if shift:
            results = [r for r in results if r["shift"] == shift]
        if building:
            results = [r for r in results if building in r["building"]]

        return {"total": len(results), "items": results}
