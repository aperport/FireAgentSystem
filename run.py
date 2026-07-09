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

