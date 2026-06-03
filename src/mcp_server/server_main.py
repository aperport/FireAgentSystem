"""

"""
from fastmcp import FastMCP
from http_base import mcp_lifespan
# 导入各个分组的注册函数
from mcp_server.server_config import MCP_HOST, MCP_PATH, MCP_PORT
from mcp_server.tools.suppliers_tools import register_supplier_tools

mcp = FastMCP(
    name="Java-Backend-MCP-Server",
    instructions="调用 Java 后端 REST API 的工具集，支持按业务分组访问",
    version="1.0.0",
    lifespan=mcp_lifespan # 关键配置
)



# 注册所有分组
register_supplier_tools(mcp)

def main():

    # 启动 Streamable HTTP 服务
    mcp.run(
        transport="streamable-http",
        host=MCP_HOST,
        port=MCP_PORT,
        path=MCP_PATH
    )
    # 注意：run() 会阻塞，且 lifespan 会在服务器关闭时自动清理资源


if __name__ == "__main__":
    main()