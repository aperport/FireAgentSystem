"""
子 Agent 中间件配置 — 提供子智能体的标准中间件工厂函数。

当前子智能体：
    fire-qa-assistant    — 知识问答助手（GraphRAG）
    fire-management-analyst — 管理分析助手（报表+评鉴）

工厂函数：
    create_qa_middleware(model, backend) — 问答助手中间件
    create_analyst_middleware(model, backend) — 管理助手中间件

子 Agent 中间件与主 Agent 中间件独立配置，
通过 subagent 配置的 middleware 字段传入。
"""

from deepagents.middleware.summarization import (
    create_summarization_tool_middleware,
)
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)

from unitl_tools.logger import get_logger

logger = get_logger(__name__)


def create_analyst_middleware(model, backend) -> list:
    """
    为 procurement-analyst 子 Agent 创建中间件列表。

    包含:
    - SummarizationToolMiddleware: 阶段完成后主动压缩上下文
    - ModelCallLimitMiddleware: 防止无限循环（最多 50 次模型调用）
    - ToolCallLimitMiddleware: 防止工具调用爆炸（最多 200 次）

    Args:
        model: 用于摘要生成的模型（建议用小模型如 deepseek-v4-flash）
        backend: 文件系统后端（用于摘要持久化）

    Returns:
        中间件实例列表
    """
    return [
        create_summarization_tool_middleware(model, backend),
        ModelCallLimitMiddleware(run_limit=50),
        ToolCallLimitMiddleware(run_limit=200),
    ]

