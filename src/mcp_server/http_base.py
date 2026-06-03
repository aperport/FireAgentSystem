"""

"""

from contextlib import asynccontextmanager
from fastmcp import FastMCP
import httpx

from mcp_server.server_config import JAVA_API_BASE_URL

@asynccontextmanager
async def mcp_lifespan(server: FastMCP):
    """
    FastMCP 生命周期管理：初始化 / 关闭 HTTP 客户端

    Args:
        server: FastMCP 实例（由框架自动传入）
    """
    # 启动时创建 HTTP 客户端（连接池）
    http_client = httpx.AsyncClient(
        base_url=JAVA_API_BASE_URL,
        timeout=30.0,
        limits=httpx.Limits(max_keepalive_connections=20, max_connections=100)
    )
    yield {"http_client": http_client}
    #关闭http客户端
    await http_client.aclose()