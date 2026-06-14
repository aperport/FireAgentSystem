"""
消防后勤智能助手 — 数据模型测试 (schema.py)

测试覆盖：
    1. FireLogisticsContext — 运行时上下文（user_id/username）
    2. UserPreferences — 用户偏好（消防领域字段 + __post_init__ 默认值）
    3. ChatRequest / ChatResponse — 聊天请求/响应
    4. Message — 消息模型（含工具调用字段）
    5. Session / SessionListResponse — 会话管理
    6. Stream*Event — SSE 流式事件模型
"""

import pytest
from datetime import datetime

from agent.schema import (
    FireLogisticsContext,
    UserPreferences,
    ChatRequest,
    ChatResponse,
    Message,
    Session,
    SessionListResponse,
    SessionMessagesResponse,
    DeleteSessionResponse,
    StreamTokenEvent,
    StreamToolStartEvent,
    StreamToolArgsEvent,
    StreamToolResultEvent,
    StreamDoneEvent,
    StreamErrorEvent,
)


# ============================================================
# FireLogisticsContext
# ============================================================

class TestFireLogisticsContext:
    """运行时上下文测试 — 消防场景替代原 ProcurementContext"""

    def test_create_with_required_fields(self):
        """必填字段 user_id 和 username 正常创建"""
        ctx = FireLogisticsContext(user_id="user001", username="张伟")
        assert ctx.user_id == "user001"
        assert ctx.username == "张伟"

    def test_create_with_empty_strings(self):
        """空字符串也是合法值（dataclass 不做内容校验）"""
        ctx = FireLogisticsContext(user_id="", username="")
        assert ctx.user_id == ""
        assert ctx.username == ""

    def test_no_extra_fields_from_procurement(self):
        """确认不再有原采购项目的 preferred_currency / recent_suppliers 字段"""
        ctx = FireLogisticsContext(user_id="u1", username="n1")
        assert not hasattr(ctx, "preferred_currency")
        assert not hasattr(ctx, "recent_suppliers")

    def test_dataclass_is_mutable(self):
        """dataclass 字段可运行时修改"""
        ctx = FireLogisticsContext(user_id="u1", username="n1")
        ctx.user_id = "u2"
        assert ctx.user_id == "u2"


# ============================================================
# UserPreferences
# ============================================================

class TestUserPreferences:
    """用户偏好测试 — 消防场景字段替代原采购字段"""

    def test_all_defaults_none(self):
        """所有字段默认为 None（__post_init__ 会修正列表字段）"""
        pref = UserPreferences()
        assert pref.preferred_output is None
        assert pref.preferred_chart_type is None
        assert pref.preferred_language is None
        # __post_init__ 将 None 列表字段转为空列表
        assert pref.recent_equipment == []
        assert pref.recent_zones == []
        assert pref.recent_queries == []

    def test_post_init_converts_none_lists(self):
        """__post_init__ 将 None 的列表字段转为空列表"""
        pref = UserPreferences(
            preferred_output="table",
            recent_equipment=None,
            recent_zones=None,
            recent_queries=None,
        )
        assert pref.recent_equipment == []
        assert pref.recent_zones == []
        assert pref.recent_queries == []

    def test_post_init_preserves_existing_lists(self):
        """__post_init__ 保留已赋值的列表"""
        pref = UserPreferences(
            recent_equipment=["烟感探测器-01", "喷淋泵-01"],
            recent_zones=["B栋3层", "ICU病房"],
            recent_queries=["本月巡检完成率"],
        )
        assert pref.recent_equipment == ["烟感探测器-01", "喷淋泵-01"]
        assert pref.recent_zones == ["B栋3层", "ICU病房"]
        assert pref.recent_queries == ["本月巡检完成率"]

    def test_fire_domain_fields_present(self):
        """确认消防领域字段存在"""
        pref = UserPreferences()
        assert hasattr(pref, "recent_equipment")
        assert hasattr(pref, "recent_zones")
        assert hasattr(pref, "recent_queries")

    def test_no_procurement_fields(self):
        """确认不再有原采购项目的字段"""
        pref = UserPreferences()
        assert not hasattr(pref, "preferred_currency")
        assert not hasattr(pref, "recent_suppliers")

    def test_chart_type_options(self):
        """图表类型字段可选值测试"""
        pref = UserPreferences(preferred_chart_type="bar")
        assert pref.preferred_chart_type == "bar"
        pref = UserPreferences(preferred_chart_type="line")
        assert pref.preferred_chart_type == "line"
        pref = UserPreferences(preferred_chart_type="pie")
        assert pref.preferred_chart_type == "pie"

    def test_language_options(self):
        """语言偏好字段可选值测试"""
        pref = UserPreferences(preferred_language="zh")
        assert pref.preferred_language == "zh"
        pref = UserPreferences(preferred_language="en")
        assert pref.preferred_language == "en"


# ============================================================
# ChatRequest / ChatResponse
# ============================================================

class TestChatRequest:
    """聊天请求模型测试"""

    def test_required_messages_field(self):
        """messages 为必填字段"""
        req = ChatRequest(messages="本月巡检完成率是多少")
        assert req.messages == "本月巡检完成率是多少"

    def test_optional_thread_id(self):
        """thread_id 为可选字段，默认 None"""
        req = ChatRequest(messages="你好")
        assert req.thread_id is None

    def test_thread_id_with_value(self):
        """thread_id 可赋值"""
        req = ChatRequest(messages="巡检数据", thread_id="thread-123")
        assert req.thread_id == "thread-123"

    def test_missing_messages_raises(self):
        """缺少必填字段 messages 应抛出验证错误"""
        with pytest.raises(Exception):
            ChatRequest()


class TestChatResponse:
    """聊天响应模型测试"""

    def test_default_messages_empty(self):
        """默认消息列表为空"""
        resp = ChatResponse(thread_id="t1")
        assert resp.messages == []

    def test_with_messages(self):
        """可赋值消息列表"""
        msg = Message(id="m1", role="user", content="你好")
        resp = ChatResponse(thread_id="t1", messages=[msg])
        assert len(resp.messages) == 1


# ============================================================
# Message
# ============================================================

class TestMessage:
    """消息模型测试 — 含工具调用信息"""

    def test_basic_message(self):
        """基本用户消息"""
        msg = Message(id="msg-001", role="user", content="B栋3层巡检完成率")
        assert msg.id == "msg-001"
        assert msg.role == "user"
        assert msg.content == "B栋3层巡检完成率"

    def test_tool_call_message(self):
        """包含工具调用信息的消息"""
        msg = Message(
            id="msg-002",
            role="assistant",
            content="",
            tool_calls=[{"name": "fire_inspection_query", "args": {"building": "B栋"}}],
            tool_call_id="tc-001",
            tool_name="fire_inspection_query",
            tool_status="calling",
        )
        assert msg.tool_calls is not None
        assert msg.tool_call_id == "tc-001"
        assert msg.tool_name == "fire_inspection_query"
        assert msg.tool_status == "calling"

    def test_tool_result_message(self):
        """工具结果消息"""
        msg = Message(
            id="msg-003",
            role="tool",
            content="",
            tool_call_id="tc-001",
            tool_name="fire_inspection_query",
            tool_status="done",
            text="巡检完成率 96.8%",
        )
        assert msg.role == "tool"
        assert msg.tool_status == "done"
        assert msg.text == "巡检完成率 96.8%"

    def test_source_field(self):
        """消息来源字段"""
        msg = Message(id="msg-004", role="assistant", content="...", source="fire-qa-assistant")
        assert msg.source == "fire-qa-assistant"

    def test_default_optional_fields(self):
        """可选字段默认为 None"""
        msg = Message(id="msg-005", role="user", content="test")
        assert msg.tool_calls is None
        assert msg.tool_call_id is None
        assert msg.source is None
        assert msg.tool_name is None
        assert msg.tool_status is None
        assert msg.text is None
        assert msg.images is None
        assert msg.args is None


# ============================================================
# Session 管理
# ============================================================

class TestSession:
    """会话模型测试"""

    def test_create_session(self):
        """创建会话"""
        now = datetime.now()
        s = Session(
            thread_id="thread-001",
            title="消防巡检咨询",
            created_at=now,
            updated_at=now,
            message_count=5,
        )
        assert s.thread_id == "thread-001"
        assert s.title == "消防巡检咨询"
        assert s.message_count == 5

    def test_default_message_count(self):
        """默认消息数为 0"""
        now = datetime.now()
        s = Session(thread_id="t1", title="test", created_at=now, updated_at=now)
        assert s.message_count == 0


class TestSessionListResponse:
    """会话列表响应测试"""

    def test_default_values(self):
        """默认值测试"""
        resp = SessionListResponse()
        assert resp.sessions == []
        assert resp.total == 0
        assert resp.page == 1
        assert resp.limit == 20

    def test_with_sessions(self):
        """带会话列表"""
        now = datetime.now()
        sessions = [
            Session(thread_id="t1", title="s1", created_at=now, updated_at=now),
            Session(thread_id="t2", title="s2", created_at=now, updated_at=now),
        ]
        resp = SessionListResponse(sessions=sessions, total=2)
        assert len(resp.sessions) == 2
        assert resp.total == 2


class TestDeleteSessionResponse:
    """删除会话响应测试"""

    def test_success_response(self):
        """成功删除"""
        resp = DeleteSessionResponse(success=True, message="会话已删除")
        assert resp.success is True

    def test_default_values(self):
        """默认值测试"""
        resp = DeleteSessionResponse()
        assert resp.success is True
        assert resp.message == "会话已删除"


# ============================================================
# SSE 流式事件
# ============================================================

class TestStreamEvents:
    """SSE 流式事件模型测试"""

    def test_stream_token_event(self):
        """Token 事件"""
        event = StreamTokenEvent(content="巡检", source="main")
        assert event.type == "token"
        assert event.content == "巡检"
        assert event.source == "main"

    def test_stream_token_event_from_subagent(self):
        """来自子智能体的 Token 事件"""
        event = StreamTokenEvent(content="查询结果", source="fire-qa-assistant")
        assert event.source == "fire-qa-assistant"

    def test_stream_tool_start_event(self):
        """工具开始调用事件"""
        event = StreamToolStartEvent(tool_call_id="tc-001", tool_name="fire_inspection_query")
        assert event.type == "tool_start"
        assert event.tool_call_id == "tc-001"
        assert event.tool_name == "fire_inspection_query"

    def test_stream_tool_args_event(self):
        """工具参数事件"""
        event = StreamToolArgsEvent(args='{"building": "B栋"}')
        assert event.type == "tool_args"
        assert event.args == '{"building": "B栋"}'

    def test_stream_tool_result_event(self):
        """工具结果事件"""
        event = StreamToolResultEvent(tool_name="fire_inspection_query", result="完成率96.8%")
        assert event.type == "tool_result"
        assert event.tool_name == "fire_inspection_query"

    def test_stream_done_event(self):
        """流结束事件"""
        event = StreamDoneEvent(thread_id="t1", content="巡检完成率96.8%")
        assert event.type == "done"
        assert event.thread_id == "t1"

    def test_stream_done_event_default_content(self):
        """流结束事件默认内容为空"""
        event = StreamDoneEvent(thread_id="t1")
        assert event.content == ""

    def test_stream_error_event(self):
        """错误事件"""
        event = StreamErrorEvent(message="MCP连接超时")
        assert event.type == "error"
        assert event.message == "MCP连接超时"
