"""
上下文摘要中间件 — 当对话过长时自动压缩历史信息。

功能：
    1. 自动摘要：当对话长度接近上下文上限（85%）时，自动压缩历史信息
    2. 主动摘要：提供 compact_conversation 工具，Agent 可在关键节点（如收到子 Agent 报告后）主动调用

工厂函数：
    build_summarization_middleware(backend, model) -> SummarizationToolMiddleware

本中间件为通用能力，无需针对消防场景做业务性改动。
参数中 model 建议使用轻量模型以节省成本（如 DeepSeek_FAST）。
"""


from typing import Union, Any

from langchain_core.language_models import BaseChatModel
from deepagents.middleware.summarization import create_summarization_tool_middleware
from deepagents.middleware.summarization import SummarizationToolMiddleware


def build_summarization_middleware(
    backend: Any,
    model: Union[str, BaseChatModel] = "DeepSeek_FAST",
) -> SummarizationToolMiddleware:
    """
    构建摘要工具中间件。

    该中间件是一个 SummarizationToolMiddleware 实例，内部自动包含了一个
    SummarizationMiddleware（负责自动摘要），并额外提供了一个名为
    `compact_conversation` 的工具，供 Agent 主动触发对话压缩。

    参数:
        backend: 沙箱后端（用于持久化被压缩的完整对话历史）。
        model: 用于生成摘要的模型，可以是字符串标识或模型实例。
               建议使用轻量、便宜的模型以节省成本（如 "gpt-4o-mini"）。

    返回:
        SummarizationToolMiddleware: 可直接传入 create_deep_agent 的 middleware 列表。

    """
    # 该工厂函数会自动创建一个 SummarizationMiddleware 并将其嵌入到
    # SummarizationToolMiddleware 中。触发阈值等参数使用框架默认值，
    # 通常为上下文达到 85% 时触发自动摘要，这已满足多数生产场景。
    return create_summarization_tool_middleware(
        model=model,
        backend=backend,
    )