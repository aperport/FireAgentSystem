"""
MCP 工具包 — 消防后勤业务工具注册。

当前工具文件：
    knowledge_tools.py       — 知识检索工具 (graph_rag_search / knowledge_search / graph_query)
    report_tools.py          — 报表评鉴工具 (fire_report_generate / fire_quality_evaluate)
    fire_equipment_tools.py  — 设备查询 (fire_equipment_query)
    fire_alarm_tools.py      — 火警/故障记录 (fire_alarm_record_query)
    fire_inspection_tools.py — 巡检记录 (fire_inspection_query)
    fire_maintenance_tools.py — 维修/维保工单 (fire_maintenance_order_query)
    fire_duty_tools.py       — 值班排班 (fire_duty_schedule_query)
    fire_utility_tools.py    — 能耗监测 (fire_utility_monitor_query)

原 suppliers_tools.py 已移除（采购场景替换为消防场景）。
"""

from mcp_server.tools.knowledge_tools import register_knowledge_tools
from mcp_server.tools.report_tools import register_report_tools
from mcp_server.tools.fire_equipment_tools import register_equipment_tools
from mcp_server.tools.fire_alarm_tools import register_alarm_tools
from mcp_server.tools.fire_inspection_tools import register_inspection_tools
from mcp_server.tools.fire_maintenance_tools import register_maintenance_tools
from mcp_server.tools.fire_duty_tools import register_duty_tools
from mcp_server.tools.fire_utility_tools import register_utility_tools

__all__ = [
    "register_knowledge_tools",
    "register_report_tools",
    "register_equipment_tools",
    "register_alarm_tools",
    "register_inspection_tools",
    "register_maintenance_tools",
    "register_duty_tools",
    "register_utility_tools",
]
