"""
pyproject.toml 或 pytest.ini 的 pytest 配置已足够，此文件提供共享 fixtures。

全局 fixtures：
    - mock_runtime: 模拟 AgentMiddleware 所需的 runtime 对象
    - mock_store: 模拟 StoreBackend (aget/aput)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone

from agent.middlewares.memory_update import MemoryEntities


@pytest.fixture
def mock_runtime():
    """
    模拟 AgentMiddleware 所需的 runtime 对象。
    包含 context (FireLogisticsContext) 和 store。
    """
    runtime = MagicMock()

    # 模拟 context — 模拟 FireLogisticsContext 的属性访问
    ctx = MagicMock()
    ctx.user_id = "test_user_001"
    ctx.username = "张伟"
    runtime.context = ctx

    # 模拟 store
    store = AsyncMock()
    store.aget = AsyncMock(return_value=None)
    store.aput = AsyncMock(return_value=None)
    runtime.store = store

    return runtime


@pytest.fixture
def mock_runtime_no_context():
    """模拟没有 context 的 runtime（测试空 context 场景）"""
    runtime = MagicMock()
    runtime.context = None
    runtime.store = AsyncMock()
    return runtime


@pytest.fixture
def mock_runtime_no_user_id():
    """模拟 context 中没有 user_id 的 runtime"""
    runtime = MagicMock()
    ctx = MagicMock()
    ctx.user_id = None
    ctx.username = None
    runtime.context = ctx
    runtime.store = AsyncMock()
    return runtime


@pytest.fixture
def mock_store_with_preferences():
    """
    模拟已有偏好文件的 StoreBackend。
    返回 (store, preferences_content) 元组。
    """
    preferences_content = {
        "content": [
            "preferred_output: table",
            "preferred_chart_type: bar",
            "preferred_language: zh",
        ],
        "created_at": "2026-06-01T00:00:00+00:00",
        "modified_at": "2026-06-01T00:00:00+00:00",
    }

    store = AsyncMock()
    mock_item = MagicMock()
    mock_item.value = preferences_content
    store.aget = AsyncMock(return_value=mock_item)
    store.aput = AsyncMock(return_value=None)

    return store, preferences_content


@pytest.fixture
def mock_llm():
    """模拟 BaseChatModel，返回固定的实体提取结果"""
    model = AsyncMock()

    # 模拟 with_structured_output 返回的结构化输出链
    structured = MagicMock()
    structured.ainvoke = AsyncMock(
        return_value=MemoryEntities(
            preferred_output="table",
            preferred_chart_type="bar",
            preferred_language="zh",
        )
    )
    model.with_structured_output = MagicMock(return_value=structured)

    return model


@pytest.fixture
def mock_llm_empty():
    """模拟返回空偏好的 LLM"""
    model = AsyncMock()
    structured = MagicMock()
    structured.ainvoke = AsyncMock(
        return_value=MemoryEntities(preferred_output=None, preferred_chart_type=None, preferred_language=None)
    )
    model.with_structured_output = MagicMock(return_value=structured)
    return model


def make_human_message(content: str) -> MagicMock:
    """构造模拟的 HumanMessage"""
    msg = MagicMock()
    msg.type = "human"
    msg.content = content
    msg.tool_calls = None
    return msg


def make_ai_message(content: str) -> MagicMock:
    """构造模拟的 AIMessage"""
    msg = MagicMock()
    msg.type = "ai"
    msg.content = content
    msg.tool_calls = None
    return msg


def make_ai_message_with_task(content: str) -> MagicMock:
    """构造模拟的带 task 工具调用的 AIMessage"""
    msg = MagicMock()
    msg.type = "ai"
    msg.content = content
    msg.tool_calls = [{"name": "task", "args": {"agent_name": "fire-qa-assistant"}}]
    return msg
