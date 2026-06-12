"""
子 Agent 中间件配置。
提供标准中间件的工厂函数，在创建 Agent 时注入。
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

def create_agent_middleware(model,backend) -> list:
    """
    为 Agent 创建中间件，用于后续加载
    包含：
        SummarizationToolMiddleware: 阶段完成后主动压缩上下文
        ModelCallLimitMiddleware: 模型调用次数限制
        ToolCallLimitMiddleware: 防止工具调用爆炸（最多 200 次）
    """

    return [create_agent_middleware(model,backend),ModelCallLimitMiddleware(),ToolCallLimitMiddleware()]
