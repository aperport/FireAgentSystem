"""
pyproject.toml 或 pytest.ini 的 pytest 配置已足够，此文件提供共享 fixtures。

全局 fixtures：
    - mock_runtime: 模拟 AgentMiddleware 所需的 runtime 对象
    - mock_store: 模拟 StoreBackend (aget/aput)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timezone


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
            "preferred_language: zh",
            "",
            "recent_equipment:",
            "  - 消火栓-08",
            "  - 喷淋泵-01",
            "",
            "recent_zones:",
            "  - A栋2层",
            "",
            "recent_queries:",
            "  - 上月巡检完成率",
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

    # 模拟 ainvoke 返回的 response
    response = MagicMock()
    response.content = '{"equipment": ["烟感探测器-01", "喷淋泵-01"], "zones": ["B栋3层"], "query": "查询B栋3层烟感设备状态"}'
    model.ainvoke = AsyncMock(return_value=response)

    return model


@pytest.fixture
def mock_llm_empty():
    """模拟返回空实体的 LLM"""
    model = AsyncMock()
    response = MagicMock()
    response.content = '{"equipment": [], "zones": [], "query": ""}'
    model.ainvoke = AsyncMock(return_value=response)
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
