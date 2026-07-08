"""
MCP 工具客户端 — 连接 MCP Server 获取所有可用工具。

在 Agent 启动时通过 langchain_mcp_adapters 的 MultiServerMCPClient
连接 MCP Server（Streamable HTTP），获取全部 MCP 工具。

对外接口：
    load_mcp_tools() -> dict[str, BaseTool]
    返回工具名到工具实例的映射，供 assemble_subagents() 分配给子 Agent。

当前 MCP Server 注册的工具：
    知识检索：graph_rag_search / knowledge_search / graph_query
    报表评鉴：fire_report_generate / fire_quality_evaluate
    业务明细：fire_equipment_query / fire_alarm_record_query / fire_inspection_query
              fire_maintenance_order_query / fire_duty_schedule_query / fire_utility_monitor_query

连接地址从环境变量 MCP_SERVER_URL 读取。
"""
from langchain_mcp_adapters.client import MultiServerMCPClient
from util_tools.logger import get_logger
from langchain.tools import BaseTool

logger = get_logger(__name__)

#MCP Server 连接配置，与魔塔空间连接类似，不过连接格式为streamable-http

ErpApiConfig = {
    "url": "http://127.0.0.1:8000/mcp",
    "transport": "streamable-http",
}
SearchConfig = {
    "command":"python",
    "args":["-m","./src/agent/tools/RAG_Tools"],
    "transport": "stidio",
}

MCP_SERVER_CONFIG = {
    "ErpApi": ErpApiConfig,
    "Search": SearchConfig
}
"""
此处为示例，方便理解一个为sse。另一个为stdi。
# 网络搜索
web_search_config = {
    "url":"https://mcp.api-inference.modelscope.net/0a7aa261f00a4e/sse",  # 注意：如果链接已失效，会导致整个加载崩溃
    "transport": "sse"
}
# 浏览器操作
Playwright_config = {
    "transport": "stdio",
    "command": "npx", # Windows系统如果报错可以尝试换成 "npx.cmd"
    "args": ["-y", "@executeautomation/playwright-mcp-server"]
}
"""
#  工具的分组规则（前缀匹配）


async def load_mcp_tools(server_config: dict | None = None) -> dict[str, BaseTool]:
    """
    连接所有MCP，加载所有工具并分组
    arg:
        server_config: MCP Server 连接配置
    return:
        
    """
    if not server_config:
        server_config = MCP_SERVER_CONFIG
    logger.info("正在连接MCP Server...")
    mcp_client = MultiServerMCPClient(server_config)

    # 从MCP Server加载工具
    tools_groups = []
    # 遍历所有Server,加载工具，对工具进行前缀命名，用于后续分组匹配
    for key in server_config:
        tools = await mcp_client.get_tools(server_name=str(key))
        new_tools = []
        for tool in tools:
            tool.name = f"{key}_{tool.name}"
            new_tools.append(tool)
        tools = new_tools
        tools_groups.append(tools)
        logger.info(f"已加载工具,共计{len(tools)}个工具，来自Server:{key}")
    all_tools = [tool for tools in tools_groups for tool in tools]
    # 返回工具及工具名称
    tool_map = {tool.name: tool for tool in all_tools}
    logger.info(f"已加载工具:{list(tool_map.keys())}")
    return tool_map

    



        

    
    