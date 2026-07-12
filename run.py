"""
消防后勤智能助手 — 项目统一入口。

支持三种运行模式：
    1. Agent 模式：启动智能助手对话（CLI）
    2. MCP Server 模式：启动 FastMCP 工具服务
    3. API Server 模式：启动 FastAPI HTTP 服务

使用方式：
    python run.py --mode agent
    python run.py --mode mcp-server
    python run.py --mode api
"""

import argparse
import asyncio
import sys
import os
import uuid

# ponytail: 确保 src/ 在搜索路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))


def run_agent():
    """Agent 模式：CLI 交互对话"""
    from langchain.messages import HumanMessage
    from langchain_core.runnables import RunnableConfig
    from src.agent.main_agent import get_agent_async
    from src.api_view.servers import query_user

    thread_id = uuid.uuid4().hex
    user = query_user(user_name="用户", thread_id=thread_id,query="")
    config = RunnableConfig(
        metadata={"user_id": user.user_id, "username": user.user_name},
        run_name=f"{user.user_name}_main_agent",
        configurable={"thread_id": thread_id, "user_id": user.user_id, "username": user.user_name},
    )

    print("消防后勤智能助手（输入 exit 退出，new 新会话）")
    print(f"会话ID: {thread_id}\n")

    async def _chat():


    asyncio.run(_chat())


def run_mcp_server():
    """MCP Server 模式：启动 FastMCP 工具服务"""
    from mcp_server.server_main import main
    main()


def run_api_server():
    """API Server 模式：启动 FastAPI HTTP 服务"""
    import uvicorn
    from src.api_view.servers import app

    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", "9000"))
    print(f"启动 API Server: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


def main():
    parser = argparse.ArgumentParser(description="消防后勤智能助手")
    parser.add_argument(
        "--mode",
        choices=["agent", "mcp-server", "api"],
        default="agent",
        help="运行模式: agent(CLI对话) / mcp-server(工具服务) / api(HTTP服务)",
    )
    args = parser.parse_args()

    if args.mode == "agent":
        run_agent()
    elif args.mode == "mcp-server":
        run_mcp_server()
    elif args.mode == "api":
        run_api_server()


if __name__ == "__main__":
    main()
