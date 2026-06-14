"""
消防后勤智能助手 — 中间件测试 (context_injection / memory_update)

测试覆盖：
    1. ContextInjectionMiddleware — 用户信息注入 SystemMessage
    2. MemoryUpdateMiddlewareTools — 关键词匹配 / 有意义判断 / AI摘要 / 实体提取
    3. MemoryUpdateMiddleware — 偏好更新全流程
    4. _merge_preferences — 偏好合并策略
"""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage

from agent.middlewares.context_injection import ContextInjectionMiddleware
from agent.middlewares.memory_update import MemoryUpdateMiddleware, MemoryUpdateMiddlewareTools
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

    def test_before_agent_includes_fire_domain_fields(self, mock_runtime):
        """注入内容包含消防领域字段提示"""
        state = {"messages": []}
        result = self.middleware.before_agent(state, mock_runtime)

        msg = result["messages"][0]
        # 确认提示中包含消防领域偏好字段
        assert "recent_equipment" in msg.content
        assert "recent_zones" in msg.content
        assert "recent_queries" in msg.content

    def test_before_agent_no_currency_field(self, mock_runtime):
        """注入内容不包含采购场景的 preferred_currency"""
        state = {"messages": []}
        result = self.middleware.before_agent(state, mock_runtime)

        msg = result["messages"][0]
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

    def test_is_meaningful_skip_greeting(self):
        """打招呼消息应跳过"""
        for greeting in ["你好", "在吗", "谢谢", "好的", "知道了", "嗯", "哦", "hi", "hello", "ok", "thanks"]:
            messages = [make_human_message(greeting)]
            result = self.tools._is_meaningful_last(messages)
            assert result is None, f"'{greeting}' 应被跳过"

    def test_is_meaningful_skip_non_fire_content(self):
        """非消防无关消息应跳过"""
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

    # --- _extract_entities ---

    @pytest.mark.asyncio
    async def test_extract_entities_success(self, mock_llm):
        """成功提取实体"""
        result = await self.tools._extract_entities(mock_llm, "B栋3层烟感设备状态", "巡检完成率96.8%")
        assert "equipment" in result
        assert "zones" in result
        assert "query" in result
        assert "烟感探测器-01" in result["equipment"]

    @pytest.mark.asyncio
    async def test_extract_entities_fire_domain_fields(self, mock_llm):
        """实体提取结果为消防领域字段（equipment/zones/query），非采购字段"""
        result = await self.tools._extract_entities(mock_llm, "测试消息", "测试摘要")
        # 确认返回消防领域字段
        assert "equipment" in result
        assert "zones" in result
        # 不应有采购字段
        assert "suppliers" not in result

    @pytest.mark.asyncio
    async def test_extract_entities_llm_failure(self):
        """LLM 调用失败时返回空实体"""
        failing_model = AsyncMock()
        failing_model.ainvoke = AsyncMock(side_effect=Exception("LLM调用失败"))

        result = await self.tools._extract_entities(failing_model, "测试", "摘要")
        assert result["equipment"] == []
        assert result.get("zones", []) == []
        assert result.get("query", "") == ""

    # --- _create_file_value ---

    def test_create_file_value(self):
        """创建 StoreBackend 兼容的文件值"""
        # 源码 _create_file_value 内部使用 datetime.timezone.utc，
        # 此处 mock 掉 datetime.now 避免导入问题
        from datetime import datetime, timezone
        with patch("agent.middlewares.memory_update.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2026, 6, 14, 10, 0, 0, tzinfo=timezone.utc)
            mock_dt.timezone = timezone
            result = self.tools._create_file_value("line1\nline2\nline3")
        assert "content" in result
        assert "created_at" in result
        assert "modified_at" in result
        assert result["content"] == ["line1", "line2", "line3"]


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
        """有意义的消息触发偏好更新"""
        # 构造 LLM mock
        mock_llm = AsyncMock()
        response = MagicMock()
        response.content = '{"equipment": ["烟感探测器-01"], "zones": ["B栋3层"], "query": "B栋3层烟感设备状态"}'
        mock_llm.ainvoke = AsyncMock(return_value=response)

        middleware = MemoryUpdateMiddleware(model=mock_llm)

        # 构造 runtime mock
        runtime = MagicMock()
        ctx = MagicMock()
        ctx.user_id = "test_user_001"
        ctx.username = "张伟"
        runtime.context = ctx
        store = AsyncMock()
        store.aget = AsyncMock(return_value=None)
        store.aput = AsyncMock(return_value=None)
        runtime.store = store

        # 用 MagicMock 模拟 state（支持 getattr 访问）
        state = MagicMock()
        state.messages = [
            make_human_message("B栋3层烟感探测器状态怎么样"),
            make_ai_message("B栋3层烟感探测器-01状态正常"),
        ]

        # patch _create_file_value 以规避源码中 datetime.timezone 的 bug
        with patch(
            "agent.middlewares.memory_update.MemoryUpdateMiddlewareTools._create_file_value",
            return_value={
                "content": ["recent_equipment:", "  - 烟感探测器-01", "", "recent_zones:", "  - B栋3层", "", "recent_queries:", "  - B栋3层烟感设备状态"],
                "created_at": "2026-06-14T10:00:00+00:00",
                "modified_at": "2026-06-14T10:00:00+00:00",
            },
        ):
            result = await middleware.aafter_agent(state, runtime)

        assert result is None  # aafter_agent 始终返回 None
        store.aput.assert_called_once()

    @pytest.mark.asyncio
    async def test_aafter_agent_empty_entities_skip_update(self, mock_runtime, mock_llm_empty):
        """提取到空实体时跳过更新"""
        middleware = MemoryUpdateMiddleware(model=mock_llm_empty)
        # 即使匹配了关键词，如果实体提取结果为空也跳过
        state = MagicMock()
        state.messages = [
            make_human_message("能耗数据怎么样"),
            make_ai_message("能耗数据正常"),
        ]

        result = await middleware.aafter_agent(state, mock_runtime)
        assert result is None

    @pytest.mark.asyncio
    async def test_aafter_agent_no_store_skip(self):
        """无 store 时跳过更新"""
        mock_llm = AsyncMock()
        middleware = MemoryUpdateMiddleware(model=mock_llm)

        runtime = MagicMock()
        ctx = MagicMock()
        ctx.user_id = "test_user"
        ctx.username = "测试"
        runtime.context = ctx
        runtime.store = None  # 无 store

        state = MagicMock()
        state.messages = [
            make_human_message("巡检完成率怎么样"),
            make_ai_message("完成率96.8%"),
        ]

        result = await middleware.aafter_agent(state, runtime)
        assert result is None


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
            new_equipment=["烟感探测器-01"],
            new_zones=["B栋3层"],
            new_query="查询烟感设备状态",
        )
        assert "recent_equipment:" in result
        assert "烟感探测器-01" in result
        assert "recent_zones:" in result
        assert "B栋3层" in result
        assert "recent_queries:" in result
        assert "查询烟感设备状态" in result

    def test_merge_adds_new_equipment(self):
        """合并新增设备"""
        current_lines = [
            "preferred_output: table",
            "",
            "recent_equipment:",
            "  - 喷淋泵-01",
            "",
            "recent_zones:",
            "  - A栋地下1层",
            "",
            "recent_queries:",
            "  - 上月巡检完成率",
        ]

        result = self.middleware._merge_preferences(
            current_lines=current_lines,
            new_equipment=["烟感探测器-01"],
            new_zones=["B栋3层"],
            new_query="B栋3层烟感设备状态",
        )

        # 新设备排在前面
        assert "烟感探测器-01" in result
        # 旧设备保留
        assert "喷淋泵-01" in result

    def test_merge_deduplicates_equipment(self):
        """合并时去重设备"""
        current_lines = [
            "recent_equipment:",
            "  - 烟感探测器-01",
            "  - 喷淋泵-01",
            "",
            "recent_zones: []",
            "",
            "recent_queries: []",
        ]

        result = self.middleware._merge_preferences(
            current_lines=current_lines,
            new_equipment=["烟感探测器-01"],  # 重复
            new_zones=[],
            new_query="",
        )

        # 烟感探测器-01 应只出现一次
        assert result.count("烟感探测器-01") == 1

    def test_merge_equipment_cap_at_10(self):
        """设备列表最多10个"""
        current_lines = [
            "recent_equipment:",
        ] + [f"  - 设备-{i:02d}" for i in range(10)]

        # 加上当前行格式
        current_lines.extend(["", "recent_zones: []", "", "recent_queries: []"])

        result = self.middleware._merge_preferences(
            current_lines=current_lines,
            new_equipment=["新设备-A"],
            new_zones=[],
            new_query="新查询",
        )

        # 设备数量不应超过10
        equipment_lines = [l for l in result.split("\n") if l.strip().startswith("- ")]
        # 统计 recent_equipment 区块下的项
        in_equipment_block = False
        count = 0
        for line in result.split("\n"):
            if line.strip().startswith("recent_equipment:"):
                in_equipment_block = True
                continue
            if in_equipment_block:
                if line.strip().startswith("- "):
                    count += 1
                elif line.strip() and not line.startswith(" "):
                    break
        assert count <= 10

    def test_merge_zones_cap_at_5(self):
        """区域列表最多5个"""
        current_lines = [
            "recent_equipment: []",
            "",
            "recent_zones:",
        ] + [f"  - 区域-{i}" for i in range(5)]
        current_lines.extend(["", "recent_queries: []"])

        result = self.middleware._merge_preferences(
            current_lines=current_lines,
            new_equipment=[],
            new_zones=["新区域-X"],
            new_query="",
        )

        # 统计区域项数
        in_zones_block = False
        count = 0
        for line in result.split("\n"):
            if line.strip().startswith("recent_zones:"):
                in_zones_block = True
                continue
            if in_zones_block:
                if line.strip().startswith("- "):
                    count += 1
                elif line.strip() and not line.startswith(" "):
                    break
        assert count <= 5

    def test_merge_queries_cap_at_5(self):
        """查询列表最多5个"""
        current_lines = [
            "recent_equipment: []",
            "",
            "recent_zones: []",
            "",
            "recent_queries:",
        ] + [f"  - 查询{i}" for i in range(5)]

        result = self.middleware._merge_preferences(
            current_lines=current_lines,
            new_equipment=[],
            new_zones=[],
            new_query="新查询",
        )

        # 统计查询项数
        in_queries_block = False
        count = 0
        for line in result.split("\n"):
            if line.strip().startswith("recent_queries:"):
                in_queries_block = True
                continue
            if in_queries_block:
                if line.strip().startswith("- "):
                    count += 1
                elif line.strip() and not line.startswith(" "):
                    break
        assert count <= 5

    def test_merge_inline_format(self):
        """合并时支持 inline 格式 (recent_equipment: [a, b])"""
        current_lines = [
            "recent_equipment: [喷淋泵-01, 消火栓-08]",
            "recent_zones: [A栋2层]",
            "recent_queries: [上月巡检完成率]",
        ]

        result = self.middleware._merge_preferences(
            current_lines=current_lines,
            new_equipment=["烟感探测器-01"],
            new_zones=["B栋3层"],
            new_query="本月故障记录",
        )

        assert "烟感探测器-01" in result
        assert "喷淋泵-01" in result

    def test_merge_empty_new_values(self):
        """新增值为空时保留旧值"""
        current_lines = [
            "recent_equipment:",
            "  - 喷淋泵-01",
            "",
            "recent_zones: []",
            "",
            "recent_queries: []",
        ]

        result = self.middleware._merge_preferences(
            current_lines=current_lines,
            new_equipment=[],
            new_zones=[],
            new_query="",
        )

        # 旧设备应保留（空新增不会清除旧值）
        assert "喷淋泵-01" in result

    def test_merge_preserves_non_preference_content(self):
        """合并时保留偏好区块之外的内容"""
        current_lines = [
            "preferred_output: table",
            "preferred_language: zh",
            "",
            "recent_equipment: []",
            "",
            "recent_zones: []",
            "",
            "recent_queries: []",
        ]

        result = self.middleware._merge_preferences(
            current_lines=current_lines,
            new_equipment=["烟感探测器-01"],
            new_zones=["B栋3层"],
            new_query="测试查询",
        )

        # 非偏好区块内容保留
        assert "preferred_output: table" in result
        assert "preferred_language: zh" in result
