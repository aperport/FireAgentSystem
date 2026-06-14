"""
能耗监测查询 MCP 工具 — 查询电能/水能实时与历史监测数据。

注册 MCP Tool：
    fire_utility_monitor_query — 查询电能/水能实时与历史监测数据

查询参数：
    - building：建筑区域
    - type：能耗类型（electric / water）
    - period：时间范围
    - metric：指标类型（有功功率/用电量/瞬时流量/累计流量/管网压力等）

返回：时间戳、指标值、单位等时序数据。

能耗指标说明：
    - 电能：有功功率(kW)、无功功率(kVar)、功率因数、日/月用电量(kWh)
    - 水能：瞬时流量(m³/h)、累计流量(m³)、管网压力(MPa)

Java后端接口：GET /utility/monitor

注意：趋势分析和同比环比应走 fire_report_generate，
本工具仅查原始明细数据，不应被用来做聚合计算。

当前为 Mock 数据模式，待接入 Java 后端后替换为 httpx 调用。
"""

from fastmcp import FastMCP


# ============================================================
# Mock 数据
# ============================================================

_MOCK_UTILITY_DATA = [
    {"timestamp": "2026-06-12 08:00", "metric": "有功功率", "value": 125.5, "unit": "kW", "building": "A栋", "type": "electric"},
    {"timestamp": "2026-06-12 08:00", "metric": "月用电量", "value": 38420.0, "unit": "kWh", "building": "A栋", "type": "electric"},
    {"timestamp": "2026-06-12 08:00", "metric": "功率因数", "value": 0.92, "unit": "-", "building": "A栋", "type": "electric"},
    {"timestamp": "2026-06-12 08:00", "metric": "有功功率", "value": 98.3, "unit": "kW", "building": "B栋", "type": "electric"},
    {"timestamp": "2026-06-12 08:00", "metric": "月用电量", "value": 28560.0, "unit": "kWh", "building": "B栋", "type": "electric"},
    {"timestamp": "2026-06-12 08:00", "metric": "功率因数", "value": 0.88, "unit": "-", "building": "B栋", "type": "electric"},
    {"timestamp": "2026-06-12 08:00", "metric": "瞬时流量", "value": 12.5, "unit": "m³/h", "building": "A栋", "type": "water"},
    {"timestamp": "2026-06-12 08:00", "metric": "累计流量", "value": 8560.0, "unit": "m³", "building": "A栋", "type": "water"},
    {"timestamp": "2026-06-12 08:00", "metric": "管网压力", "value": 0.35, "unit": "MPa", "building": "A栋", "type": "water"},
    {"timestamp": "2026-06-12 08:00", "metric": "瞬时流量", "value": 8.2, "unit": "m³/h", "building": "B栋", "type": "water"},
    {"timestamp": "2026-06-12 08:00", "metric": "累计流量", "value": 5430.0, "unit": "m³", "building": "B栋", "type": "water"},
    {"timestamp": "2026-06-12 08:00", "metric": "管网压力", "value": 0.32, "unit": "MPa", "building": "B栋", "type": "water"},
    {"timestamp": "2026-06-11 08:00", "metric": "有功功率", "value": 118.0, "unit": "kW", "building": "A栋", "type": "electric"},
    {"timestamp": "2026-06-11 08:00", "metric": "月用电量", "value": 37200.0, "unit": "kWh", "building": "A栋", "type": "electric"},
    {"timestamp": "2026-06-10 08:00", "metric": "有功功率", "value": 130.0, "unit": "kW", "building": "A栋", "type": "electric"},
    {"timestamp": "2026-06-10 08:00", "metric": "月用电量", "value": 36000.0, "unit": "kWh", "building": "A栋", "type": "electric"},
]


def register_utility_tools(mcp: FastMCP):
    """注册能耗监测查询工具到 MCP Server"""

    @mcp.tool(name="fire_utility_monitor_query")
    async def fire_utility_monitor_query(
        building: str | None = None,
        type: str | None = None,
        period: str | None = None,
        metric: str | None = None,
    ) -> dict:
        """
        查询电能/水能监测数据。支持按建筑、能耗类型、指标过滤。
        不要用于趋势分析和同比环比，聚合统计应走 fire_report_generate。

        Args:
            building: 建筑区域，如"A栋"、"B栋"
            type: 能耗类型，可选：electric/water
            period: 时间范围（暂未使用）
            metric: 指标类型，可选：有功功率/用电量/瞬时流量/累计流量/管网压力/功率因数

        Returns:
            能耗数据查询结果，包含 total 和 items 列表
        """
        # TODO: 接入Java后端后替换为 httpx 调用

        results = list(_MOCK_UTILITY_DATA)

        if building:
            results = [r for r in results if building in r["building"]]
        if type:
            results = [r for r in results if r["type"] == type]
        if metric:
            results = [r for r in results if metric in r["metric"]]

        return {"total": len(results), "items": results}
