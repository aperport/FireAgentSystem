"""
消防设备查询 MCP 工具 — 查询消防设备台账明细。

注册 MCP Tool：
    fire_equipment_query — 按名称/位置/类型查询消防设备信息

查询参数：
    - name：设备名称（模糊查询）
    - location：安装位置（如 B栋3楼）
    - category：设备分类（火灾探测类/报警类/灭火类/通风排烟类/疏散类/电气类）

返回：设备编号、名称、安装位置、设备类型、当前状态、最近检测时间等。

Java后端接口：GET /equipment/search

当前为 Mock 数据模式，待接入 Java 后端后替换为 httpx 调用。
"""

from fastmcp import FastMCP


# ============================================================
# Mock 数据
# ============================================================

_MOCK_EQUIPMENT = [
    {"id": "EQ-001", "name": "烟感探测器-01", "location": "B栋3层", "category": "火灾探测类", "status": "正常", "install_date": "2024-03-15", "last_check_date": "2026-05-20"},
    {"id": "EQ-002", "name": "喷淋泵-01", "location": "A栋地下1层", "category": "灭火类", "status": "正常", "install_date": "2023-08-20", "last_check_date": "2026-06-01"},
    {"id": "EQ-003", "name": "排烟风机-02", "location": "B栋4层", "category": "通风排烟类", "status": "故障", "install_date": "2023-05-10", "last_check_date": "2026-04-18"},
    {"id": "EQ-004", "name": "EPS电源-01", "location": "A栋配电间", "category": "电气类", "status": "正常", "install_date": "2022-11-30", "last_check_date": "2026-05-28"},
    {"id": "EQ-005", "name": "消防广播-03", "location": "C栋1层大厅", "category": "疏散类", "status": "正常", "install_date": "2024-01-08", "last_check_date": "2026-06-05"},
    {"id": "EQ-006", "name": "手动报警按钮-12", "location": "B栋3层走廊", "category": "报警类", "status": "正常", "install_date": "2024-06-22", "last_check_date": "2026-05-30"},
    {"id": "EQ-007", "name": "消火栓-08", "location": "A栋2层", "category": "灭火类", "status": "维修中", "install_date": "2022-03-14", "last_check_date": "2026-04-25"},
    {"id": "EQ-008", "name": "温感探测器-05", "location": "ICU病房", "category": "火灾探测类", "status": "正常", "install_date": "2024-09-01", "last_check_date": "2026-06-10"},
    {"id": "EQ-009", "name": "防火卷帘门-02", "location": "B栋1层通道", "category": "疏散类", "status": "正常", "install_date": "2023-12-05", "last_check_date": "2026-05-15"},
    {"id": "EQ-010", "name": "气体灭火控制器-01", "location": "A栋机房", "category": "灭火类", "status": "正常", "install_date": "2024-02-18", "last_check_date": "2026-06-02"},
]


def register_equipment_tools(mcp: FastMCP):
    """注册消防设备查询工具到 MCP Server"""

    @mcp.tool(name="fire_equipment_query")
    async def fire_equipment_query(
        name: str | None = None,
        location: str | None = None,
        category: str | None = None,
    ) -> dict:
        """
        查询消防设备台账明细。支持按名称、位置、分类模糊查询。
        不要用于聚合统计，聚合统计应走 fire_report_generate。

        Args:
            name: 设备名称（模糊查询），如"烟感"、"喷淋泵"
            location: 安装位置（模糊查询），如"B栋3层"、"ICU"
            category: 设备分类，可选：火灾探测类/报警类/灭火类/通风排烟类/疏散类/电气类

        Returns:
            设备查询结果，包含 total 和 items 列表
        """
        # TODO: 接入Java后端后替换为 httpx 调用
        # async with httpx.AsyncClient() as client:
        #     resp = await client.get(f"{JAVA_API_BASE_URL}/equipment/search", params={...})
        #     return resp.json()

        results = list(_MOCK_EQUIPMENT)

        if name:
            results = [d for d in results if name in d["name"]]
        if location:
            results = [d for d in results if location in d["location"]]
        if category:
            results = [d for d in results if category in d["category"]]

        return {"total": len(results), "items": results}
