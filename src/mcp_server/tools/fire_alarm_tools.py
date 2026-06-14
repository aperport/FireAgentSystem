"""
火警/故障记录查询 MCP 工具 — 查询火警报警和设备故障记录。

注册 MCP Tool：
    fire_alarm_record_query — 按时间范围/状态查询火警和故障报警记录

查询参数：
    - start_date / end_date：时间范围（yyyy-MM-dd）
    - status：报警状态（待处理/处理中/已恢复）
    - building：建筑区域过滤
    - alarm_type：报警类型（火警/故障/预警）

返回：报警时间、设备名称、报警类型、状态、处理人、恢复时间等。

Java后端接口：GET /alarm/records

当前为 Mock 数据模式，待接入 Java 后端后替换为 httpx 调用。
"""

from fastmcp import FastMCP


# ============================================================
# Mock 数据
# ============================================================

_MOCK_ALARM_RECORDS = [
    {"id": "ALM-001", "alarm_time": "2026-06-12 08:23:45", "equipment_name": "烟感探测器-01", "alarm_type": "火警", "status": "已恢复", "location": "B栋3层", "handler": "张伟", "recover_time": "2026-06-12 08:35:12"},
    {"id": "ALM-002", "alarm_time": "2026-06-11 14:05:30", "equipment_name": "排烟风机-02", "alarm_type": "故障", "status": "处理中", "location": "B栋4层", "handler": "李强", "recover_time": None},
    {"id": "ALM-003", "alarm_time": "2026-06-10 22:18:00", "equipment_name": "温感探测器-05", "alarm_type": "预警", "status": "已恢复", "location": "ICU病房", "handler": "王芳", "recover_time": "2026-06-10 22:30:45"},
    {"id": "ALM-004", "alarm_time": "2026-06-09 03:45:22", "equipment_name": "手动报警按钮-12", "alarm_type": "火警", "status": "已恢复", "location": "B栋3层走廊", "handler": "赵军", "recover_time": "2026-06-09 04:10:08"},
    {"id": "ALM-005", "alarm_time": "2026-06-08 10:12:55", "equipment_name": "EPS电源-01", "alarm_type": "故障", "status": "待处理", "location": "A栋配电间", "handler": None, "recover_time": None},
    {"id": "ALM-006", "alarm_time": "2026-06-07 16:30:00", "equipment_name": "消火栓-08", "alarm_type": "故障", "status": "已恢复", "location": "A栋2层", "handler": "陈明", "recover_time": "2026-06-07 18:20:30"},
    {"id": "ALM-007", "alarm_time": "2026-06-05 09:55:10", "equipment_name": "烟感探测器-01", "alarm_type": "预警", "status": "已恢复", "location": "B栋3层", "handler": "张伟", "recover_time": "2026-06-05 10:05:22"},
    {"id": "ALM-008", "alarm_time": "2026-06-03 21:08:33", "equipment_name": "防火卷帘门-02", "alarm_type": "故障", "status": "已恢复", "location": "B栋1层通道", "handler": "李强", "recover_time": "2026-06-04 09:15:00"},
]


def register_alarm_tools(mcp: FastMCP):
    """注册火警/故障记录查询工具到 MCP Server"""

    @mcp.tool(name="fire_alarm_record_query")
    async def fire_alarm_record_query(
        start_date: str | None = None,
        end_date: str | None = None,
        status: str | None = None,
        building: str | None = None,
        alarm_type: str | None = None,
    ) -> dict:
        """
        查询火警报警和设备故障记录。支持按时间、状态、区域、类型过滤。
        不要用于聚合统计（报警频次/误报率），聚合统计应走 fire_report_generate。

        Args:
            start_date: 起始日期（yyyy-MM-dd）
            end_date: 结束日期（yyyy-MM-dd）
            status: 报警状态，可选：待处理/处理中/已恢复
            building: 建筑区域过滤，如"A栋"、"B栋"
            alarm_type: 报警类型，可选：火警/故障/预警

        Returns:
            报警记录查询结果，包含 total 和 items 列表
        """
        # TODO: 接入Java后端后替换为 httpx 调用

        results = list(_MOCK_ALARM_RECORDS)

        if start_date:
            results = [r for r in results if r["alarm_time"] >= start_date]
        if end_date:
            results = [r for r in results if r["alarm_time"] <= end_date + " 23:59:59"]
        if status:
            results = [r for r in results if r["status"] == status]
        if building:
            results = [r for r in results if building in r["location"]]
        if alarm_type:
            results = [r for r in results if r["alarm_type"] == alarm_type]

        return {"total": len(results), "items": results}
