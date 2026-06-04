"""
MCP 工具客户端。

在 Agent 启动时连接所有 MCP Server，获取全部 MCP 工具，
并按分组筛选后分配给不同的子 Agent。

"""
from langchain_mcp_adapters.client import MultiServerMCPClient
from unitl_tools.logger import get_logger
from langchain.tools import BaseTool

logger = get_logger(__name__)

#MCP Server 连接配置，与魔塔空间连接类似，不过连接格式为streamable-http
MCP_SERVER_CONFIG = {
    "erp_api":{
        "url": "http://127.0.0.1:8000/mcp",
        "transport": "streamable-http",
    }
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
    for key in server_config:
        tools = await mcp_client.get_tools(server_name=str(key))
        tools_groups.append(tools)
        logger.info(f"已加载工具,共计{len(tools)}个工具，来自Server:{key}")
    all_tools = [tool for tools in tools_groups for tool in tools]
    # 返回工具及工具名称
    tool_map = {tool.name: tool for tool in all_tools}
    logger.info(f"已加载工具:{list(tool_map.keys())}")
    return tool_map

    



        

    
    