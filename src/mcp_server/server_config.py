"""
MCP Server 连接配置 — 管理 MCP 服务端和 Java 后端的连接信息。

所有配置从 graph_rag.config.get_settings() 统一读取，
不再各自 os.getenv() 或 load_dotenv()。
"""

from graph_rag.config import get_settings


def _get_config():
    s = get_settings()
    return s


JAVA_API_BASE_URL = property(lambda self: _get_config().java_api_base_url)
MCP_HOST = property(lambda self: _get_config().mcp_host)
MCP_PORT = property(lambda self: _get_config().mcp_port)
MCP_PATH = property(lambda self: _get_config().mcp_path)


# ponytail: 保持模块级变量兼容旧代码 `from mcp_server.server_config import MCP_HOST`
_s = _get_config()
JAVA_API_BASE_URL = _s.java_api_base_url
MCP_HOST = _s.mcp_host
MCP_PORT = _s.mcp_port
MCP_PATH = _s.mcp_path
