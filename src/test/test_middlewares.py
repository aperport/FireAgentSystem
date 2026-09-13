"""
消防后勤智能助手 — 中间件测试 (context_injection / memory_update)

测试覆盖：
    1. ContextInjectionMiddleware — 用户信息注入 SystemMessage
    2. MemoryUpdateMiddlewareTools — 关键词匹配 / 有意义判断 / AI摘要 / 偏好提取
    3. MemoryUpdateMiddleware — 偏好更新全流程
    4. _merge_preferences — 偏好合并策略
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import SystemMessage

from agent.middlewares.context_injection import ContextInjectionMiddleware
from agent.middlewares.memory_update import MemoryEntities, MemoryUpdateMiddleware, MemoryUpdateMiddlewareTools
from test.conftest import make_human_message, make_ai_message, make_ai_message_with_task


# ============================================================
# ContextInjectionMiddleware
# ============================================================

class TestContextInjectionMiddleware:
    """上下文注入中间件测试"""

    def setup_method(self):
        self.middleware = ContextInjectionMiddleware()

    def test_before_agent_with_valid_context(self, mock_runtime):
        """正常上下文注入 — 返回 SystemMessage"""
        state = {"messages": []}
        result = self.middleware.before_agent(state, mock_runtime)

        assert result is not None
        assert "messages" in result
        assert len(result["messages"]) == 1

        msg = result["messages"][0]
        assert isinstance(msg, SystemMessage)
        assert "test_user_001" in msg.content
        assert "张伟" in msg.content
        assert "/memories/test_user_001/preferences.md" in msg.content

    def test_before_agent_includes_preference_fields(self, mock_runtime):
        """注入内容包含个人偏好字段提示"""
        state = {"messages": []}
        result = self.middleware.before_agent(state, mock_runtime)

        msg = result["messages"][0]
        # 确认提示中包含个人偏好字段
        assert "preferred_output" in msg.content
        assert "preferred_chart_type" in msg.content
        assert "preferred_language" in msg.content

    def test_before_agent_no_deprecated_recent_fields(self, mock_runtime):
        """注入内容不再包含已废弃的 recent_* 字段与采购字段"""
        state = {"messages": []}
        result = self.middleware.before_agent(state, mock_runtime)

        msg = result["messages"][0]
        assert "recent_equipment" not in msg.content
        assert "recent_zones" not in msg.content
        assert "recent_queries" not in msg.content
        assert "preferred_currency" not in msg.content
        assert "recent_suppliers" not in msg.content

    def test_before_agent_empty_context(self, mock_runtime_no_context):
        """context 为空时跳过注入"""
        state = {"messages": []}
        result = self.middleware.before_agent(state, mock_runtime_no_context)

        assert result is None

    def test_before_agent_no_user_id(self, mock_runtime_no_user_id):
        """user_id 为空时跳过注入"""
        state = {"messages": []}
        result = self.middleware.before_agent(state, mock_runtime_no_user_id)

        assert result is None

    def test_before_agent_uses_username_when_available(self, mock_runtime):
        """有 username 时使用 username"""
        state = {"messages": []}
        result = self.middleware.before_agent(state, mock_runtime)

        msg = result["messages"][0]
        assert "张伟" in msg.content

    def test_before_agent_fallback_to_user_id_as_name(self):
        """无 username 时使用 user_id 作为显示名"""
        middleware = ContextInjectionMiddleware()
        runtime = MagicMock()
        ctx = MagicMock()
        ctx.user_id = "user_abc"
        ctx.username = None  # username 为空
        runtime.context = ctx

        state = {"messages": []}
        result = middleware.before_agent(state, runtime)

        msg = result["messages"][0]
        assert "user_abc" in msg.content

    @pytest.mark.asyncio
    async def test_abefore_agent_delegates_to_before_agent(self, mock_runtime):
        """异步方法 abefore_agent 委托给同步方法"""
        state = {"messages": []}
        result = await self.middleware.abefore_agent(state, mock_runtime)

        assert result is not None
        assert "messages" in result


# ============================================================
# MemoryUpdateMiddlewareTools
# ============================================================

class TestMemoryUpdateMiddlewareTools:
    """记忆更新中间件工具类测试"""

    def setup_method(self):
        self.tools = MemoryUpdateMiddlewareTools()

    # --- _is_meaningful_last ---

    def test_is_meaningful_with_fire_keyword(self):
        """包含消防关键词的消息有意义"""
        messages = [make_human_message("B栋3层巡检完成率怎么样")]
        result = self.tools._is_meaningful_last(messages)
        assert result is not None
        assert "巡检" in result

    def test_is_meaningful_with_multiple_keywords(self):
        """包含多个消防关键词的消息有意义"""
        messages = [make_human_message("EPS电源故障影响了哪些设备？")]
        result = self.tools._is_meaningful_last(messages)
        assert result is not None
        assert "故障" in result

    def test_is_meaningful_with_preference_keyword(self):
        """包含输出偏好表达的消息有意义（无需业务关键词）"""
        for text in ["以后用表格展示", "请用折线图呈现", "用英文回复"]:
            messages = [make_human_message(text)]
            result = self.tools._is_meaningful_last(messages)
            assert result is not None, f"'{text}' 应被视为有意义"

    def test_is_meaningful_skip_greeting(self):
        """打招呼消息应跳过"""
        for greeting in ["你好", "在吗", "谢谢", "好的", "知道了", "嗯", "哦", "hi", "hello", "ok", "thanks"]:
            messages = [make_human_message(greeting)]
            result = self.tools._is_meaningful_last(messages)
            assert result is None, f"'{greeting}' 应被跳过"

    def test_is_meaningful_skip_non_fire_content(self):
        """无关内容（无业务关键词/偏好词/子Agent调用）应跳过"""
        messages = [make_human_message("今天天气怎么样？")]
        result = self.tools._is_meaningful_last(messages)
        assert result is None

    def test_is_meaningful_with_subagent_call(self):
        """有子Agent委派调用即使无关键词也有意义"""
        # 构造: human消息 + AI的task工具调用消息
        messages = [
            make_human_message("帮我查一下系统使用方法"),
            make_ai_message_with_task("正在委派..."),
        ]
        result = self.tools._is_meaningful_last(messages)
        assert result is not None

    def test_is_meaningful_empty_messages(self):
        """空消息列表返回 None"""
        result = self.tools._is_meaningful_last([])
        assert result is None

    def test_is_meaningful_no_human_message(self):
        """没有 HumanMessage 返回 None"""
        messages = [make_ai_message("AI回复内容")]
        result = self.tools._is_meaningful_last(messages)
        assert result is None

    def test_is_meaningful_empty_content(self):
        """空内容的用户消息返回 None"""
        messages = [make_human_message("")]
        result = self.tools._is_meaningful_last(messages)
        assert result is None

    def test_is_meaningful_fire_keywords_list(self):
        """确认消防关键词列表完整"""
        expected_keywords = ["巡检", "维保", "火警", "故障", "能耗", "值班", "用电", "用水", "用气"]
        for kw in expected_keywords:
            assert kw in self.tools.business_keywords, f"缺少关键词: {kw}"

    def test_is_meaningful_no_procurement_keywords(self):
        """确认不再包含采购领域关键词"""
        procurement_keywords = ["供应商", "采购", "零件", "报价", "货币"]
        for kw in procurement_keywords:
            assert kw not in self.tools.business_keywords, f"不应包含采购关键词: {kw}"

    # --- _extract_ai_summary ---

    def test_extract_ai_summary(self):
        """正常提取 AI 摘要"""
        long_content = "这是AI的回复内容" * 50  # 超过300字符
        messages = [
            make_human_message("问题"),
            make_ai_message(long_content),
        ]
        result = self.tools._extract_ai_summary(messages)
        assert result is not None
        assert len(result) <= 300

    def test_extract_ai_summary_short(self):
        """AI 回复不足300字符时完整返回"""
        messages = [
            make_human_message("问题"),
            make_ai_message("B栋3层巡检完成率为96.8%"),
        ]
        result = self.tools._extract_ai_summary(messages)
        assert result == "B栋3层巡检完成率为96.8%"

    def test_extract_ai_summary_no_ai_message(self):
        """没有 AI 消息返回空字符串"""
        messages = [make_human_message("问题")]
        result = self.tools._extract_ai_summary(messages)
        assert result == ""

    # --- _extract_preferences ---

    @pytest.mark.asyncio
    async def test_extract_preferences_success(self, mock_llm):
        """成功提取输出偏好"""
        result = await self.tools._extract_preferences(mock_llm, "请用表格展示巡检数据", "已完成")
        assert "preferred_output" in result
        assert "preferred_chart_type" in result
        assert "preferred_language" in result
        assert result["preferred_output"] == "table"

    @pytest.mark.asyncio
    async def test_extract_preferences_preference_fields(self, mock_llm):
        """偏好提取结果为个人偏好字段，不再包含实体/近期字段"""
        result = await self.tools._extract_preferences(mock_llm, "测试消息", "测试摘要")
        # 确认返回个人偏好字段
        assert "preferred_output" in result
        assert "preferred_chart_type" in result
        assert "preferred_language" in result
        # 不应有实体/近期字段
        assert "equipment" not in result
        assert "zones" not in result
        assert "query" not in result

    @pytest.mark.asyncio
    async def test_extract_preferences_llm_failure(self):
        """LLM 调用失败时返回空偏好"""
        failing_model = AsyncMock()
        structured = MagicMock()
        structured.ainvoke = AsyncMock(side_effect=Exception("LLM调用失败"))
        failing_model.with_structured_output = MagicMock(return_value=structured)

        result = await self.tools._extract_preferences(failing_model, "测试", "摘要")
        assert result["preferred_output"] is None
        assert result["preferred_chart_type"] is None
        assert result["preferred_language"] is None


# ============================================================
# MemoryUpdateMiddleware
# ============================================================

class TestMemoryUpdateMiddleware:
    """记忆更新中间件测试"""

    def setup_method(self):
        self.mock_model = AsyncMock()
        self.middleware = MemoryUpdateMiddleware(model=self.mock_model)

    def test_after_agent_returns_none(self):
        """同步 after_agent 钩子不做操作"""
        result = self.middleware.after_agent({}, MagicMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_aafter_agent_no_context(self, mock_runtime_no_context):
        """无 context 时跳过更新"""
        state = MagicMock()
        state.messages = [make_human_message("巡检完成率"), make_ai_message("96.8%")]
        result = await self.middleware.aafter_agent(state, mock_runtime_no_context)
        assert result is None

    @pytest.mark.asyncio
    async def test_aafter_agent_no_user_id(self, mock_runtime_no_user_id):
        """无 user_id 时跳过更新"""
        state = MagicMock()
        state.messages = [make_human_message("巡检完成率"), make_ai_message("96.8%")]
        result = await self.middleware.aafter_agent(state, mock_runtime_no_user_id)
        assert result is None

    @pytest.mark.asyncio
    async def test_aafter_agent_no_messages(self, mock_runtime):
        """无消息时跳过更新"""
        # 用 MagicMock 模拟 state（支持 getattr 访问）
        state = MagicMock()
        state.messages = []  # getattr(state, "messages", []) 返回空列表
        result = await self.middleware.aafter_agent(state, mock_runtime)
        assert result is None

    @pytest.mark.asyncio
    async def test_aafter_agent_skip_greeting(self, mock_runtime):
        """打招呼消息跳过更新"""
        state = MagicMock()
        state.messages = [make_human_message("你好")]
        result = await self.middleware.aafter_agent(state, mock_runtime)
        assert result is None

    @pytest.mark.asyncio
    async def test_aafter_agent_meaningful_message_triggers_update(self):
        """有意义的消息触发本地偏好更新"""
        # 构造 LLM mock
        mock_llm = AsyncMock()
        structured = MagicMock()
        structured.ainvoke = AsyncMock(
            return_value=MemoryEntities(
                preferred_output="table",
                preferred_chart_type="bar",
                preferred_language="zh",
            )
        )
        mock_llm.with_structured_output = MagicMock(return_value=structured)

        middleware = MemoryUpdateMiddleware(model=mock_llm)

        # 构造 runtime mock
        runtime = MagicMock()
        ctx = MagicMock()
        ctx.user_id = "test_user_001"
        ctx.username = "张伟"
        runtime.context = ctx

        # 用 MagicMock 模拟 state（支持 getattr 访问）
        state = MagicMock()
        state.messages = [
            make_human_message("以后都用表格展示巡检数据"),
            make_ai_message("好的，后续将以表格形式展示"),
        ]

        with patch("agent.middlewares.memory_update.read_preferences", return_value=""), \
             patch("agent.middlewares.memory_update.write_preferences") as mock_write:
            result = await middleware.aafter_agent(state, runtime)

        assert result is None  # aafter_agent 始终返回 None
        mock_write.assert_called_once()
        write_user_id, write_content = mock_write.call_args[0]
        assert write_user_id == "test_user_001"
        assert "preferred_output: table" in write_content
        assert "preferred_chart_type: bar" in write_content
        assert "preferred_language: zh" in write_content

    @pytest.mark.asyncio
    async def test_aafter_agent_empty_preferences_skip_update(self, mock_runtime, mock_llm_empty):
        """提取到空偏好时跳过更新"""
        middleware = MemoryUpdateMiddleware(model=mock_llm_empty)
        # 即使匹配了关键词，如果偏好提取结果为空也跳过
        state = MagicMock()
        state.messages = [
            make_human_message("能耗数据怎么样"),
            make_ai_message("能耗数据正常"),
        ]

        result = await middleware.aafter_agent(state, mock_runtime)
        assert result is None

    @pytest.mark.asyncio
    async def test_aafter_agent_write_failure_skip(self):
        """本地偏好文件写入失败时优雅跳过，不影响对话"""
        mock_llm = AsyncMock()
        structured = MagicMock()
        structured.ainvoke = AsyncMock(
            return_value=MemoryEntities(preferred_output="table", preferred_chart_type=None, preferred_language=None)
        )
        mock_llm.with_structured_output = MagicMock(return_value=structured)
        middleware = MemoryUpdateMiddleware(model=mock_llm)

        runtime = MagicMock()
        ctx = MagicMock()
        ctx.user_id = "test_user"
        ctx.username = "测试"
        runtime.context = ctx

        state = MagicMock()
        state.messages = [
            make_human_message("用表格展示巡检结果"),
            make_ai_message("好的"),
        ]

        with patch("agent.middlewares.memory_update.read_preferences", return_value=""), \
             patch(
                 "agent.middlewares.memory_update.write_preferences",
                 side_effect=OSError("磁盘写入失败"),
             ):
            result = await middleware.aafter_agent(state, runtime)

        assert result is None  # 异常被捕获，优雅跳过


# ============================================================
# _merge_preferences
# ============================================================

class TestMergePreferences:
    """偏好合并策略测试"""

    def setup_method(self):
        self.mock_model = AsyncMock()
        self.middleware = MemoryUpdateMiddleware(model=self.mock_model)

    def test_merge_into_empty_preferences(self):
        """从空偏好文件开始合并"""
        result = self.middleware._merge_preferences(
            current_lines=[],
            preferred_output="table",
            preferred_chart_type="bar",
            preferred_language="zh",
        )
        assert "preferred_output: table" in result
        assert "preferred_chart_type: bar" in result
        assert "preferred_language: zh" in result

    def test_merge_into_empty_preferences_all_none(self):
        """全部偏好为空时返回空文件"""
        result = self.middleware._merge_preferences(
            current_lines=[],
            preferred_output=None,
            preferred_chart_type=None,
            preferred_language=None,
        )
        assert result == "\n"

    def test_merge_new_value_overrides_old(self):
        """新偏好值覆盖旧值"""
        current_lines = [
            "preferred_output: table",
            "preferred_chart_type: pie",
            "preferred_language: en",
        ]

        result = self.middleware._merge_preferences(
            current_lines=current_lines,
            preferred_output="chart",
            preferred_chart_type=None,
            preferred_language=None,
        )

        # 新值覆盖旧值，未变更的字段保留旧值
        assert "preferred_output: chart" in result
        assert "preferred_chart_type: pie" in result
        assert "preferred_language: en" in result
        # 旧值不应残留
        assert "preferred_output: table" not in result

    def test_merge_empty_new_value_keeps_old(self):
        """新增值为空时保留旧值"""
        current_lines = [
            "preferred_output: table",
        ]

        result = self.middleware._merge_preferences(
            current_lines=current_lines,
            preferred_output=None,
            preferred_chart_type=None,
            preferred_language=None,
        )

        assert "preferred_output: table" in result

    def test_merge_cleans_deprecated_recent_fields(self):
        """合并时清理已废弃的 recent_* 区块"""
        current_lines = [
            "preferred_output: table",
            "",
            "recent_equipment:",
            "  - 烟感探测器-01",
            "  - 喷淋泵-01",
            "",
            "recent_zones:",
            "  - A栋2层",
            "",
            "recent_queries:",
            "  - 上月巡检完成率",
        ]

        result = self.middleware._merge_preferences(
            current_lines=current_lines,
            preferred_output=None,
            preferred_chart_type="bar",
            preferred_language=None,
        )

        assert "preferred_output: table" in result
        assert "preferred_chart_type: bar" in result
        # 废弃区块应被清除
        assert "recent_equipment" not in result
        assert "recent_zones" not in result
        assert "recent_queries" not in result
        assert "烟感探测器-01" not in result

    def test_merge_preserves_other_content(self):
        """合并时保留偏好字段之外的内容"""
        current_lines = [
            "# 用户备注",
            "关注重点区域: 手术室/ICU",
            "",
            "preferred_output: table",
            "preferred_language: zh",
        ]

        result = self.middleware._merge_preferences(
            current_lines=current_lines,
            preferred_output=None,
            preferred_chart_type="line",
            preferred_language=None,
        )

        # 非偏好字段内容保留
        assert "# 用户备注" in result
        assert "关注重点区域: 手术室/ICU" in result
        assert "preferred_output: table" in result
        assert "preferred_chart_type: line" in result
        assert "preferred_language: zh" in result
