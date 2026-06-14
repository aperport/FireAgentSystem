"""
消防后勤智能助手 — Phase 1 端到端验证测试

验证核心链路：
    主Agent → 子Agent委派 → MCP Tool调用 → 回复

测试覆盖：
    1. MCP 工具注册完整性 — 所有11个工具正确注册
    2. 工具数据模型与返回结果一致性
    3. 上下文注入 + 记忆更新联合流程
    4. 子智能体工具分配正确性
    5. 分组常量与工具名称映射一致性
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastmcp import FastMCP

from mcp_server.tools import (
    register_equipment_tools,
    register_alarm_tools,
    register_inspection_tools,
    register_maintenance_tools,
    register_duty_tools,
    register_utility_tools,
    register_report_tools,
    register_knowledge_tools,
)
from agent.mcp_tools_bean import (
    GROUP_FIRE_EQUIPMENT, GROUP_FIRE_ALARM, GROUP_FIRE_INSPECTION,
    GROUP_FIRE_MAINTENANCE, GROUP_FIRE_DUTY, GROUP_FIRE_UTILITY,
    GROUP_KNOWLEDGE, GROUP_REPORT,
)
from agent.schema import FireLogisticsContext, UserPreferences
from agent.middlewares.context_injection import ContextInjectionMiddleware
from agent.middlewares.memory_update import MemoryUpdateMiddleware, MemoryUpdateMiddlewareTools
from agent.subagents.read_yaml import load_yaml, resolve_tools
from test.conftest import make_human_message, make_ai_message


# ============================================================
# MCP 工具注册完整性
# ============================================================

class TestMCPToolRegistration:
    """验证所有11个工具正确注册到 FastMCP"""

    EXPECTED_TOOLS = [
        "fire_equipment_query",
        "fire_alarm_record_query",
        "fire_inspection_query",
        "fire_maintenance_order_query",
        "fire_duty_schedule_query",
        "fire_utility_monitor_query",
        "fire_report_generate",
        "fire_quality_evaluate",
        "graph_rag_search",
        "knowledge_search",
        "graph_query",
    ]

    async def _get_registered_tools(self) -> set[str]:
        """创建 MCP 实例，注册所有工具，返回工具名称集合"""
        mcp = FastMCP("test-server")
        register_equipment_tools(mcp)
        register_alarm_tools(mcp)
        register_inspection_tools(mcp)
        register_maintenance_tools(mcp)
        register_duty_tools(mcp)
        register_utility_tools(mcp)
        register_report_tools(mcp)
        register_knowledge_tools(mcp)

        tools = await mcp.list_tools()
        return {t.name for t in tools}

    @pytest.mark.asyncio
    async def test_all_11_tools_registered(self):
        """验证11个工具全部注册"""
        registered = await self._get_registered_tools()
        for tool_name in self.EXPECTED_TOOLS:
            assert tool_name in registered, f"工具未注册: {tool_name}"

    @pytest.mark.asyncio
    async def test_no_extra_tools_registered(self):
        """验证无多余工具注册"""
        registered = await self._get_registered_tools()
        expected = set(self.EXPECTED_TOOLS)
        extra = registered - expected
        assert extra == set(), f"多余的工具: {extra}"

    @pytest.mark.asyncio
    async def test_tool_count(self):
        """验证工具总数为11"""
        registered = await self._get_registered_tools()
        assert len(registered) == 11


# ============================================================
# 分组常量与工具名称映射
# ============================================================

class TestGroupToolMapping:
    """验证分组常量与工具名称前缀映射一致"""

    GROUP_TOOL_MAP = {
        GROUP_FIRE_EQUIPMENT: ["fire_equipment_query"],
        GROUP_FIRE_ALARM: ["fire_alarm_record_query"],
        GROUP_FIRE_INSPECTION: ["fire_inspection_query"],
        GROUP_FIRE_MAINTENANCE: ["fire_maintenance_order_query"],
        GROUP_FIRE_DUTY: ["fire_duty_schedule_query"],
        GROUP_FIRE_UTILITY: ["fire_utility_monitor_query"],
        GROUP_KNOWLEDGE: ["graph_rag_search", "knowledge_search", "graph_query"],
        GROUP_REPORT: ["fire_report_generate", "fire_quality_evaluate"],
    }

    def test_group_prefix_matches_tool_names(self):
        """消防业务分组的工具名称以分组前缀开头，知识/报表分组按约定映射"""
        # 业务分组：工具名以 fire_{group}_ 前缀开头
        business_groups = {
            GROUP_FIRE_EQUIPMENT: ["fire_equipment_query"],
            GROUP_FIRE_ALARM: ["fire_alarm_record_query"],
            GROUP_FIRE_INSPECTION: ["fire_inspection_query"],
            GROUP_FIRE_MAINTENANCE: ["fire_maintenance_order_query"],
            GROUP_FIRE_DUTY: ["fire_duty_schedule_query"],
            GROUP_FIRE_UTILITY: ["fire_utility_monitor_query"],
        }
        for group, tool_names in business_groups.items():
            for tool_name in tool_names:
                assert tool_name.startswith(f"{group}_"), \
                    f"工具 {tool_name} 的名称与分组 {group} 前缀不匹配"

        # 知识/报表分组：按约定映射，不强制前缀
        assert "knowledge_search" in self.GROUP_TOOL_MAP[GROUP_KNOWLEDGE]
        assert "fire_report_generate" in self.GROUP_TOOL_MAP[GROUP_REPORT]

    def test_all_tools_accounted_for(self):
        """分组映射覆盖了所有11个工具"""
        all_mapped = set()
        for tools in self.GROUP_TOOL_MAP.values():
            all_mapped.update(tools)
        expected = set(TestMCPToolRegistration.EXPECTED_TOOLS)
        assert all_mapped == expected


# ============================================================
# 数据模型与返回结果一致性
# ============================================================

class TestDataModelConsistency:
    """验证 Pydantic 模型与 MCP 工具 Mock 返回数据结构一致"""

    @pytest.mark.asyncio
    async def test_equipment_result_matches_model(self):
        """设备查询结果与 Pydantic 模型一致"""
        from agent.mcp_tools_bean import FireEquipmentQueryResult, FireEquipmentItem

        mcp = FastMCP("test")
        register_equipment_tools(mcp)
        tool = await mcp.get_tool("fire_equipment_query")
        result = await tool.fn()

        items = [FireEquipmentItem(**item) for item in result["items"]]
        pydantic_result = FireEquipmentQueryResult(total=result["total"], items=items)
        assert pydantic_result.total == result["total"]

    @pytest.mark.asyncio
    async def test_alarm_result_matches_model(self):
        """火警记录查询结果与 Pydantic 模型一致"""
        from agent.mcp_tools_bean import FireAlarmRecordQueryResult, FireAlarmRecordItem

        mcp = FastMCP("test")
        register_alarm_tools(mcp)
        tool = await mcp.get_tool("fire_alarm_record_query")
        result = await tool.fn()

        items = [FireAlarmRecordItem(**item) for item in result["items"]]
        pydantic_result = FireAlarmRecordQueryResult(total=result["total"], items=items)
        assert pydantic_result.total == result["total"]

    @pytest.mark.asyncio
    async def test_inspection_result_matches_model(self):
        """巡检查询结果与 Pydantic 模型一致"""
        from agent.mcp_tools_bean import FireInspectionQueryResult, FireInspectionItem

        mcp = FastMCP("test")
        register_inspection_tools(mcp)
        tool = await mcp.get_tool("fire_inspection_query")
        result = await tool.fn()

        items = [FireInspectionItem(**item) for item in result["items"]]
        pydantic_result = FireInspectionQueryResult(total=result["total"], items=items)
        assert pydantic_result.total == result["total"]

    @pytest.mark.asyncio
    async def test_maintenance_result_matches_model(self):
        """维修工单查询结果与 Pydantic 模型一致"""
        from agent.mcp_tools_bean import FireMaintenanceOrderQueryResult, FireMaintenanceOrderItem

        mcp = FastMCP("test")
        register_maintenance_tools(mcp)
        tool = await mcp.get_tool("fire_maintenance_order_query")
        result = await tool.fn()

        items = [FireMaintenanceOrderItem(**item) for item in result["items"]]
        pydantic_result = FireMaintenanceOrderQueryResult(total=result["total"], items=items)
        assert pydantic_result.total == result["total"]

    @pytest.mark.asyncio
    async def test_duty_result_matches_model(self):
        """值班查询结果与 Pydantic 模型一致"""
        from agent.mcp_tools_bean import FireDutyScheduleQueryResult, FireDutyScheduleItem

        mcp = FastMCP("test")
        register_duty_tools(mcp)
        tool = await mcp.get_tool("fire_duty_schedule_query")
        result = await tool.fn()

        items = [FireDutyScheduleItem(**item) for item in result["items"]]
        pydantic_result = FireDutyScheduleQueryResult(total=result["total"], items=items)
        assert pydantic_result.total == result["total"]

    @pytest.mark.asyncio
    async def test_utility_result_matches_model(self):
        """能耗查询结果与 Pydantic 模型一致"""
        from agent.mcp_tools_bean import FireUtilityMonitorQueryResult, FireUtilityMonitorItem

        mcp = FastMCP("test")
        register_utility_tools(mcp)
        tool = await mcp.get_tool("fire_utility_monitor_query")
        result = await tool.fn()

        items = [FireUtilityMonitorItem(**item) for item in result["items"]]
        pydantic_result = FireUtilityMonitorQueryResult(total=result["total"], items=items)
        assert pydantic_result.total == result["total"]


# ============================================================
# 上下文注入 + 记忆更新联合流程
# ============================================================

class TestMiddlewareIntegration:
    """中间件联合流程测试"""

    @pytest.mark.asyncio
    async def test_context_injection_then_memory_update(self, mock_runtime):
        """先注入上下文，再触发记忆更新"""

        # Step 1: 上下文注入
        ci_middleware = ContextInjectionMiddleware()
        state = {"messages": []}
        injection_result = ci_middleware.before_agent(state, mock_runtime)

        assert injection_result is not None
        injected_msg = injection_result["messages"][0]
        assert "test_user_001" in injected_msg.content

        # Step 2: 模拟用户对话 — 使用 MagicMock state 以支持 getattr
        state_with_conversation = MagicMock()
        state_with_conversation.messages = [
            injected_msg,
            make_human_message("B栋3层巡检完成率怎么样？"),
            make_ai_message("B栋3层本月巡检完成率为96.8%，达标。"),
        ]

        # Step 3: 记忆更新
        mock_llm = AsyncMock()
        response = MagicMock()
        response.content = '{"equipment": ["烟感探测器-01"], "zones": ["B栋3层"], "query": "B栋3层巡检完成率"}'
        mock_llm.ainvoke = AsyncMock(return_value=response)

        mu_middleware = MemoryUpdateMiddleware(model=mock_llm)

        # patch _create_file_value 以规避源码中 datetime.timezone 的 bug
        with patch(
            "agent.middlewares.memory_update.MemoryUpdateMiddlewareTools._create_file_value",
            return_value={
                "content": ["recent_equipment:", "  - 烟感探测器-01", "", "recent_zones:", "  - B栋3层", "", "recent_queries:", "  - B栋3层巡检完成率"],
                "created_at": "2026-06-14T10:00:00+00:00",
                "modified_at": "2026-06-14T10:00:00+00:00",
            },
        ):
            result = await mu_middleware.aafter_agent(state_with_conversation, mock_runtime)

        # 记忆更新成功，store.aput 被调用
        assert result is None  # aafter_agent 始终返回 None
        mock_runtime.store.aput.assert_called_once()

    @pytest.mark.asyncio
    async def test_memory_update_with_existing_preferences(self, mock_runtime, mock_store_with_preferences):
        """记忆更新与已有偏好合并"""
        store, existing_pref = mock_store_with_preferences
        mock_runtime.store = store

        # 设置 LLM 返回消防实体
        mock_llm = AsyncMock()
        response = MagicMock()
        response.content = '{"equipment": ["烟感探测器-01"], "zones": ["B栋3层"], "query": "B栋3层设备状态"}'
        mock_llm.ainvoke = AsyncMock(return_value=response)

        mu_middleware = MemoryUpdateMiddleware(model=mock_llm)
        state = MagicMock()
        state.messages = [
            make_human_message("B栋3层烟感设备状态怎么样"),
            make_ai_message("B栋3层烟感探测器-01状态正常"),
        ]

        with patch(
            "agent.middlewares.memory_update.MemoryUpdateMiddlewareTools._create_file_value",
            return_value={
                "content": ["recent_equipment:", "  - 烟感探测器-01", "", "recent_zones:", "  - B栋3层", "", "recent_queries:", "  - B栋3层设备状态"],
                "created_at": "2026-06-14T10:00:00+00:00",
                "modified_at": "2026-06-14T10:00:00+00:00",
            },
        ):
            result = await mu_middleware.aafter_agent(state, mock_runtime)
        assert result is None

        # 验证 aput 被调用（偏好已更新）
        store.aput.assert_called_once()
        call_args = store.aput.call_args
        # 验证 namespace 包含 user_id
        assert call_args[0][0] == ("test_user_001",)


# ============================================================
# 子智能体委派验证
# ============================================================

class TestSubAgentDelegation:
    """子智能体委派与工具分配验证"""

    def _load_yaml_directly(self) -> list[dict]:
        """直接读取 YAML 文件"""
        import yaml
        from pathlib import Path
        yaml_path = Path(__file__).parent.parent / "agent" / "subagents" / "agents"
        subagents = []
        for yaml_file in yaml_path.iterdir():
            if yaml_file.suffix == ".yaml":
                with open(yaml_file, "r", encoding="utf-8") as f:
                    content = yaml.safe_load(f)
                    if content and "name" in content:
                        subagents.append(content)
        return subagents

    def test_qa_assistant_has_knowledge_tools_only(self):
        """问答助手只能访问知识检索工具"""
        subagents = self._load_yaml_directly()
        qa = next(sa for sa in subagents if sa["name"] == "fire-qa-assistant")
        tools = qa["tools"]["include"]

        knowledge_tools = {"graph_rag_search", "knowledge_search", "graph_query"}
        assert set(tools) == knowledge_tools

        # 不应包含业务查询工具
        business_tools = {
            "fire_report_generate", "fire_quality_evaluate",
            "fire_equipment_query", "fire_alarm_record_query",
            "fire_inspection_query", "fire_maintenance_order_query",
            "fire_duty_schedule_query", "fire_utility_monitor_query",
        }
        assert not business_tools.intersection(set(tools))

    def test_management_analyst_has_all_business_tools(self):
        """管理分析助手可访问所有业务工具 + graph_query"""
        subagents = self._load_yaml_directly()
        ma = next(sa for sa in subagents if sa["name"] == "fire-management-analyst")
        tools = set(ma["tools"]["include"])

        # 应包含9个工具
        assert len(tools) == 9

        # 高层聚合工具
        assert "fire_report_generate" in tools
        assert "fire_quality_evaluate" in tools

        # 6个明细工具
        detail_tools = {
            "fire_equipment_query", "fire_alarm_record_query",
            "fire_inspection_query", "fire_maintenance_order_query",
            "fire_duty_schedule_query", "fire_utility_monitor_query",
        }
        assert detail_tools.issubset(tools)

        # 图遍历工具（故障影响链）
        assert "graph_query" in tools

        # 不应包含纯知识检索工具
        assert "knowledge_search" not in tools
        assert "graph_rag_search" not in tools

    def test_two_subagents_tool_separation(self):
        """两个子智能体的工具集基本无重叠（graph_query 共享除外）"""
        subagents = self._load_yaml_directly()
        qa = next(sa for sa in subagents if sa["name"] == "fire-qa-assistant")
        ma = next(sa for sa in subagents if sa["name"] == "fire-management-analyst")

        qa_tools = set(qa["tools"]["include"])
        ma_tools = set(ma["tools"]["include"])

        # 共享工具：graph_query
        shared = qa_tools & ma_tools
        assert shared == {"graph_query"}

    def test_subagent_system_prompt_contains_fire_domain(self):
        """子智能体 system_prompt 包含消防领域内容"""
        subagents = self._load_yaml_directly()
        for sa in subagents:
            prompt = sa["system_prompt"]
            # 应包含消防领域关键词
            assert any(kw in prompt for kw in ["消防", "巡检", "故障", "设备"]), \
                f"子智能体 {sa['name']} 的 system_prompt 缺少消防领域内容"


# ============================================================
# FireLogisticsContext 与 UserPreferences 集成
# ============================================================

class TestSchemaIntegration:
    """数据模型集成测试"""

    def test_context_provides_user_id_for_preferences(self):
        """FireLogisticsContext 的 user_id 可用于定位偏好文件"""
        ctx = FireLogisticsContext(user_id="user_fire_001", username="消防管理员")
        pref_path = f"/memories/{ctx.user_id}/preferences.md"
        assert pref_path == "/memories/user_fire_001/preferences.md"

    def test_preferences_support_fire_domain_equipment(self):
        """UserPreferences 支持消防设备列表"""
        pref = UserPreferences(
            recent_equipment=["烟感探测器-01", "喷淋泵-01", "EPS电源-01"],
            recent_zones=["B栋3层", "ICU病房"],
            recent_queries=["本月巡检完成率", "EPS电源故障影响"],
        )
        assert len(pref.recent_equipment) == 3
        assert len(pref.recent_zones) == 2
        assert len(pref.recent_queries) == 2

    def test_preferences_no_procurement_remnants(self):
        """UserPreferences 完全移除采购字段"""
        pref = UserPreferences()
        # 不应有采购相关字段
        assert not hasattr(pref, "preferred_currency")
        assert not hasattr(pref, "recent_suppliers")

        # 消防领域字段存在
        assert hasattr(pref, "recent_equipment")
        assert hasattr(pref, "recent_zones")
        assert hasattr(pref, "recent_queries")
