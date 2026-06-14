"""
消防巡检查询 MCP 工具 — 查询巡检记录与巡检计划。

注册 MCP Tool：
    fire_inspection_query — 查询巡检执行记录和巡检计划

查询参数：
    - building / floor：建筑区域过滤
    - period：时间范围
    - status：巡检状态（待执行/已完成/逾期/跳过）

返回：巡检任务、执行人、完成时间、检查项数、异常发现数等。

Java后端接口：GET /inspection/records

注意：聚合统计（完成率/逾期率）应走 fire_report_generate，
本工具仅查明细记录，不应被用来做聚合计算。

当前为 Mock 数据模式，待接入 Java 后端后替换为 httpx 调用。
"""

from fastmcp import FastMCP


# ============================================================
# Mock 数据
# ============================================================

_MOCK_INSPECTION_RECORDS = [
    {"id": "INS-001", "task_name": "B栋3层消防设施日常巡检", "executor": "张伟", "building": "B栋3层", "status": "已完成", "completed_at": "2026-06-12 10:30:00", "check_items_count": 15, "abnormal_count": 0},
    {"id": "INS-002", "task_name": "A栋地下1层灭火系统巡检", "executor": "李强", "building": "A栋地下1层", "status": "已完成", "completed_at": "2026-06-12 14:20:00", "check_items_count": 20, "abnormal_count": 2},
    {"id": "INS-003", "task_name": "ICU病房消防设备专项巡检", "executor": "王芳", "building": "ICU病房", "status": "逾期", "completed_at": None, "check_items_count": 12, "abnormal_count": 0},
    {"id": "INS-004", "task_name": "C栋1层大厅疏散设施巡检", "executor": "赵军", "building": "C栋1层", "status": "已完成", "completed_at": "2026-06-11 09:15:00", "check_items_count": 10, "abnormal_count": 1},
    {"id": "INS-005", "task_name": "A栋2层消火栓系统巡检", "executor": "陈明", "building": "A栋2层", "status": "待执行", "completed_at": None, "check_items_count": 8, "abnormal_count": 0},
    {"id": "INS-006", "task_name": "B栋4层排烟系统周巡检", "executor": "李强", "building": "B栋4层", "status": "已完成", "completed_at": "2026-06-10 16:45:00", "check_items_count": 6, "abnormal_count": 1},
    {"id": "INS-007", "task_name": "A栋配电间电气消防巡检", "executor": "张伟", "building": "A栋配电间", "status": "已完成", "completed_at": "2026-06-09 11:00:00", "check_items_count": 18, "abnormal_count": 0},
    {"id": "INS-008", "task_name": "B栋1层通道防火卷帘巡检", "executor": "王芳", "building": "B栋1层", "status": "跳过", "completed_at": None, "check_items_count": 5, "abnormal_count": 0},
]


def register_inspection_tools(mcp: FastMCP):
    """注册巡检查询工具到 MCP Server"""

    @mcp.tool(name="fire_inspection_query")
    async def fire_inspection_query(
        building: str | None = None,
        floor: str | None = None,
        period: str | None = None,
        status: str | None = None,
    ) -> dict:
        """
        查询巡检执行记录明细。支持按区域、时间、状态过滤。
        不要用于聚合统计（完成率/逾期率），聚合统计应走 fire_report_generate。

        Args:
            building: 建筑区域过滤，如"A栋"、"B栋3层"、"ICU"
            floor: 楼层过滤（暂未使用）
            period: 时间范围，如"2026-06"
            status: 巡检状态，可选：待执行/已完成/逾期/跳过

        Returns:
            巡检记录查询结果，包含 total 和 items 列表
        """
        # TODO: 接入Java后端后替换为 httpx 调用

        results = list(_MOCK_INSPECTION_RECORDS)

        if building:
            results = [r for r in results if building in r["building"]]
        if status:
            results = [r for r in results if r["status"] == status]

        return {"total": len(results), "items": results}
