"""
MCP Server 连接配置 — 管理 MCP 服务端和 Java 后端的连接信息。

配置项：
    JAVA_API_BASE_URL — Java 后端 REST API 地址（从环境变量读取，默认 http://127.0.0.1:8000）
    MCP_HOST          — MCP Server 监听地址
    MCP_PORT          — MCP Server 监听端口（注意：不应与 Java 后端端口冲突）
    MCP_PATH          — MCP Server HTTP 路径

注意：所有硬编码地址应逐步迁移到 .env 环境变量。
"""
# 后端API地址
JAVA_API_BASE_URL = "http://127.0.0.1:8000"

# MCP服务器监听
MCP_HOST = "127.0.0.1"
MCP_PORT = 8000
MCP_PATH = "/mcp"