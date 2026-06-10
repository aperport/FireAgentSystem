"""
摘要中间件：
功能：
1. 当上下文长度达到agent限制值时，自动进行摘要，压缩上下文长度
2. 提供 compact_conversation 工具，Agent 可在关键节点（如收到子 Agent 报告后）主动调用。
"""
from unitl_tools.logger import get_logger
from langchain_core.language_models import BaseChatModel
from deepagents.middleware.summarization import create_summarization_tool_middleware
from deepagents.middleware.summarization import SummarizationToolMiddleware
from deepagents.backends import CompositeBackend


logger = get_logger(__name__)


def build_sunnarizationMiddleware(backend:CompositeBackend,model:BaseChatModel | str ) ->SummarizationToolMiddleware:
    """
    构建摘要工具中间件。

    该中间件是一个 SummarizationToolMiddleware 实例，内部自动包含了一个
    SummarizationMiddleware（负责自动摘要），并额外提供了一个名为
    `compact_conversation` 的工具，供 Agent 主动触发对话压缩。
    args:
        backed:CompositeBackend 沙箱后端（用于持久化被压缩的完整对话历史）
        model:BaseChatModel | str  用于生成摘要的模型，可以是字符串标识或模型实例。
    return:
        SummarizationToolMiddleware:可直接传入 create_deep_agent 的 middleware 列表。
    """
    
    # 该工厂函数会自动创建一个 SummarizationMiddleware 并将其嵌入到
    # SummarizationToolMiddleware 中。触发阈值等参数使用框架默认值，
    # 通常为上下文达到 85% 时触发自动摘要，这已满足多数生产场景。
    
    return create_summarization_tool_middleware(
        model=model,
        backend=backend,
    )