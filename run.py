"""
消防后勤智能助手 — 项目统一入口。

支持两种运行模式：
    1. Agent 模式：启动智能助手对话（CLI）
    2. MCP Server 模式：启动 FastMCP 工具服务

使用方式：
    python run.py --mode agent
    python run.py --mode mcp-server
"""

import argparse
import asyncio
import sys
import os

# ponytail: 确保 src/ 在搜索路径中
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from mcp_server.server_main import main as mcp_server_main
from mcp_server.server_config import MCP_HOST, MCP_PORT


async def run_agent_cli():
    """Agent CLI 模式：命令行交互对话"""
    from agent.main_agent import get_agent_async
    from agent.schema import FireLogisticsContext
    from langchain_core.runnables import RunnableConfig
    import uuid

    print("=" * 50)
    print("  消防后勤智能助手 — 命令行对话模式")
    print("=" * 50)
    print("输入 'quit' 或 'exit' 退出对话\n")

    # 初始化 Agent（懒加载）
    print("正在初始化 Agent...")
    agent = await get_agent_async()
    print("Agent 初始化完成，开始对话！\n")

    # 生成会话 ID（连续对话使用同一 thread_id）
    thread_id = str(uuid.uuid4())

    while True:
        try:
            user_input = input("你: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("quit", "exit", "q"):
                print("再见！")
                break

            # 构建上下文
            context = FireLogisticsContext(
                user_id="cli_user",
                username="CLI_User",
            )
            config = RunnableConfig(
                configurable={"thread_id": thread_id},
                context=context,
            )

            # 调用 Agent
            print("Agent: ", end="", flush=True)
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": user_input}]},
                config=config,
            )

            # 提取并打印回复
            messages = result.get("messages", [])
            if messages:
                last_message = messages[-1]
                content = getattr(last_message, "content", str(last_message))
                print(content)
            else:
                print("(无回复)")

        except KeyboardInterrupt:
            print("\n再见！")
            break
        except Exception as e:
            print(f"\n[错误] {e}")
            import traceback
            traceback.print_exc()


def run_mcp_server():
    """MCP Server 模式：启动 FastMCP 工具服务"""
    print(f"启动 MCP Server: http://{MCP_HOST}:{MCP_PORT}/mcp")
    mcp_server_main()


def main():
    parser = argparse.ArgumentParser(description="消防后勤智能助手")
    parser.add_argument(
        "--mode",
        choices=["agent", "mcp-server"],
        default="agent",
        help="运行模式: agent (默认) 或 mcp-server",
    )
    args = parser.parse_args()

    if args.mode == "agent":
        asyncio.run(run_agent_cli())
    elif args.mode == "mcp-server":
        run_mcp_server()


if __name__ == "__main__":
    main()
