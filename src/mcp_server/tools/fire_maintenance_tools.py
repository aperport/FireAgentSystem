"""
消防维修/维保工单查询 MCP 工具 — 查询维修和维保工单明细。

注册 MCP Tool：
    fire_maintenance_order_query — 查询维修/维保工单

查询参数：
    - order_id：工单编号（精确查询）
    - status：工单状态（待派单/已派单/维修中/已完成/已验收/已取消）
    - type：工单类型（维修/维保）
    - building：建筑区域过滤

返回：工单编号、类型、设备名称、状态、派工人、完成时间等。

工单状态流转：
    1-待派单 → 2-已派单 → 3-维修中 → 4-已完成 → 5-已验收
                                             ↓
                                       6-已取消（待派单/已派单可取消）

Java后端接口：GET /maintenance/orders

注意：聚合统计（完工率/响应时长）应走 fire_report_generate，
本工具仅查明细记录，不应被用来做聚合计算。

当前为 Mock 数据模式，待接入 Java 后端后替换为 httpx 调用。
"""

from fastmcp import FastMCP


# ============================================================
# Mock 数据
# ============================================================

_MOCK_MAINTENANCE_ORDERS = [
    {"order_id": "MO-202606-001", "type": "维修", "equipment_name": "排烟风机-02", "status": "维修中", "building": "B栋4层", "dispatcher": "李强", "created_at": "2026-06-11", "completed_at": None, "description": "排烟风机异响，需检查轴承和叶轮"},
    {"order_id": "MO-202606-002", "type": "维修", "equipment_name": "消火栓-08", "status": "已派单", "building": "A栋2层", "dispatcher": "陈明", "created_at": "2026-06-10", "completed_at": None, "description": "消火栓出水压力不足，疑似管道堵塞"},
    {"order_id": "MO-202606-003", "type": "维保", "equipment_name": "EPS电源-01", "status": "已完成", "building": "A栋配电间", "dispatcher": "张伟", "created_at": "2026-06-05", "completed_at": "2026-06-06", "description": "EPS电源月度例行维保，蓄电池检测+切换测试"},
    {"order_id": "MO-202605-004", "type": "维修", "equipment_name": "防火卷帘门-02", "status": "已验收", "building": "B栋1层通道", "dispatcher": "王芳", "created_at": "2026-05-28", "completed_at": "2026-05-30", "description": "防火卷帘门下降不顺畅，导轨清洁+润滑"},
    {"order_id": "MO-202605-005", "type": "维保", "equipment_name": "喷淋泵-01", "status": "已验收", "building": "A栋地下1层", "dispatcher": "李强", "created_at": "2026-05-20", "completed_at": "2026-05-22", "description": "喷淋泵季度维保，运行测试+密封件检查"},
    {"order_id": "MO-202606-006", "type": "维修", "equipment_name": "EPS电源-01", "status": "待派单", "building": "A栋配电间", "dispatcher": None, "created_at": "2026-06-13", "completed_at": None, "description": "EPS电源报警，需检查蓄电池状态"},
    {"order_id": "MO-202606-007", "type": "维保", "equipment_name": "烟感探测器-01", "status": "已完成", "building": "B栋3层", "dispatcher": "赵军", "created_at": "2026-06-01", "completed_at": "2026-06-02", "description": "烟感探测器半年清洁标定"},
    {"order_id": "MO-202605-008", "type": "维修", "equipment_name": "消防广播-03", "status": "已取消", "building": "C栋1层大厅", "dispatcher": None, "created_at": "2026-05-15", "completed_at": None, "description": "广播音量偏小，后排查为接线问题已自行修复"},
]


def register_maintenance_tools(mcp: FastMCP):
    """注册维修/维保工单查询工具到 MCP Server"""

    @mcp.tool(name="fire_maintenance_order_query")
    async def fire_maintenance_order_query(
        order_id: str | None = None,
        status: str | None = None,
        type: str | None = None,
        building: str | None = None,
    ) -> dict:
        """
        查询维修/维保工单明细。支持按工单号、状态、类型、区域过滤。
        不要用于聚合统计（完工率/响应时长），聚合统计应走 fire_report_generate。

        Args:
            order_id: 工单编号（精确查询），如"MO-202606-001"
            status: 工单状态，可选：待派单/已派单/维修中/已完成/已验收/已取消
            type: 工单类型，可选：维修/维保
            building: 建筑区域过滤，如"A栋"、"B栋"

        Returns:
            工单查询结果，包含 total 和 items 列表
        """
        # TODO: 接入Java后端后替换为 httpx 调用

        results = list(_MOCK_MAINTENANCE_ORDERS)

        if order_id:
            results = [r for r in results if r["order_id"] == order_id]
        if status:
            results = [r for r in results if r["status"] == status]
        if type:
            results = [r for r in results if r["type"] == type]
        if building:
            results = [r for r in results if building in r["building"]]

        return {"total": len(results), "items": results}
