"""
MCP Server 入口 — FastMCP Streamable HTTP 服务，注册所有消防后勤业务工具。
"""

from fastmcp import FastMCP
from mcp_server.http_base import mcp_lifespan
from mcp_server.server_config import MCP_HOST, MCP_PATH, MCP_PORT
from mcp_server.tools import (
    register_knowledge_tools,
    register_report_tools,
    register_equipment_tools,
    register_alarm_tools,
    register_inspection_tools,
    register_maintenance_tools,
    register_duty_tools,
    register_utility_tools,
)

mcp = FastMCP(
    name="Fire-Logistics-MCP-Server",
    instructions="消防后勤智能助手 MCP 工具集，支持知识检索、报表评鉴、业务明细查询",
    version="1.0.0",
    lifespan=mcp_lifespan,
)

# 注册所有工具分组
register_knowledge_tools(mcp)
register_report_tools(mcp)
register_equipment_tools(mcp)
register_alarm_tools(mcp)
register_inspection_tools(mcp)
register_maintenance_tools(mcp)
register_duty_tools(mcp)
register_utility_tools(mcp)


def main():
    """启动 MCP Streamable HTTP 服务"""
    mcp.run(
        transport="streamable-http",
        host=MCP_HOST,
        port=MCP_PORT,
        path=MCP_PATH,
    )


if __name__ == "__main__":
    main()
