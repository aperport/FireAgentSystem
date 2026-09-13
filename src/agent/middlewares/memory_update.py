"""
记忆更新中间件 — 在每轮 Agent 回复完成后自动更新用户偏好文件。

Hook: aafter_agent

功能：
    自动提取对话中用户表达的输出偏好（输出格式/图表类型/回复语言），
    更新本地偏好文件（data/memories/{user_id}/preferences.md）。
    Agent 无需手动维护 preferred_output / preferred_chart_type / preferred_language —— 系统自动处理。
    近期动态（recent_equipment / recent_zones / recent_queries）不再持久化，
    仅依赖短期记忆（checkpointer 会话级），长期只保留稳定的个人偏好。

处理流程：
    1. 获取 user_id（从 runtime.context）
    2. 判断最后一条用户消息是否"有意义"（闲聊过滤 + 业务/偏好关键词 + 子Agent委派检测）
    3. LLM 提取输出偏好（preferred_output / preferred_chart_type / preferred_language）
    4. 合并更新本地 preferences.md

优化：
    - 使用 `with_structured_output` 结构化输出
    - 可考虑写入数据库如 MongoDB 进行存储

使用方式:
    from agent.middlewares.memory_update import MemoryUpdateMiddleware
    middleware = MemoryUpdateMiddleware(model=SUMMARY_MODEL)
"""

from typing import Any, Dict

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import AgentState
from langchain.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from pydantic import BaseModel, Field

from agent.memory.preferences_store import read_preferences, write_preferences
from util_tools.logger import get_logger

logger = get_logger(__name__)


class MemoryEntities(BaseModel):
    """LLM 偏好提取的结构化输出模型"""

    preferred_output: str | None = Field(
        default=None,
        description="用户偏好的输出格式：'table'(表格) / 'chart'(图表) / 'text'(纯文本)，未表达则为 None",
    )
    preferred_chart_type: str | None = Field(
        default=None,
        description="用户偏好的图表类型：'bar'(柱状图) / 'line'(折线图) / 'pie'(饼图) 等，未表达则为 None",
    )
    preferred_language: str | None = Field(
        default=None,
        description="用户偏好的回复语言：'zh'(中文) / 'en'(英文) 等，未表达则为 None",
    )


class MemoryUpdateMiddlewareTools:
    def __init__(self):
        self.business_keywords = [
            "巡检",
            "维保",
            "火警",
            "故障",
            "能耗",
            "值班",
            "用电",
            "用水",
            "用气",
            "烟感",
            "喷淋",
            "设备",
            "消火栓",
            "报警",
            "探测器",
            "灭火",
            "消防",
            "配电",
            "泵",
            "电源",
        ]
        # 用户表达输出偏好的关键词（如"请用表格展示"、"用折线图"、"英文回复"）
        self.preference_keywords = [
            "表格",
            "图表",
            "列表",
            "可视化",
            "展示",
            "柱状图",
            "条形图",
            "折线图",
            "饼图",
            "趋势图",
            "英文",
            "中文",
            "语言",
            "格式",
            "排版",
            "样式",
            "table",
            "chart",
            "bar",
            "line",
            "pie",
        ]
        self.skip_words = [
            "你好",
            "在吗",
            "谢谢",
            "好的",
            "知道了",
            "嗯",
            "哦",
            "hi",
            "hello",
            "ok",
            "thanks",
        ]

    def _is_meaningful_last(self, message: list[BaseMessage]) -> str | None:
        """
        判断最后一条用户消息是否有意义
        """
        last_user_message = None
        # 使用反向迭代迭代message，根据type判断，寻找最后一条用户信息，找到最后一条结束循环
        for msg in reversed(message):
            msg_type = getattr(msg, "type", None)
            if msg_type == "human":
                last_user_message = msg
                break
        # 如果没找到用户消息或者最后一条用户消息为空，返回None
        if not last_user_message:
            return None

        content = last_user_message.content
        if isinstance(content, list):
            content = " ".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
        content = str(content).strip()  # 去两边空格

        if not content:
            return None

        # 跳过无意义消息
        content_lower = content.lower().replace(" ", "")  # 删除字符串空格
        for pattern in self.skip_words:
            if pattern.lower().replace(" ", "") in content_lower:
                return None

        # 检查是否包含业务关键词或偏好表达关键词
        has_keyword = any(
            keyword.lower() in content_lower for keyword in self.business_keywords
        ) or any(
            keyword.lower() in content_lower for keyword in self.preference_keywords
        )

        # 兜底：检查是否委派了子 Agent（messages 中有 task 工具调用）(工具调用这一块需要灵活修改)
        if not has_keyword:
            has_subagent_call = False
            for msg in message:
                if hasattr(msg, "tool_calls") and msg.tool_calls:  # type: ignore # 检查对象里是否含有特定属性hasattr
                    for tc in msg.tool_calls:  # type: ignore # 检查对象里是否含有特定属性hasattr
                        if tc.get("name") == "task":
                            has_subagent_call = True
                            break
                if has_subagent_call:
                    break
            if not has_subagent_call:
                return None

        return content

    def _extract_ai_summary(self, message: list[BaseMessage]) -> str | None:
        """
        提取最后一条AI消息的前300字符作为摘要
        """
        for msg in reversed(message):
            if getattr(msg, "type", None) == "ai":
                content = msg.content
                if isinstance(content, list):
                    content = " ".join(
                        part.get("text", "") if isinstance(part, dict) else str(part) for part in content
                    )
                content = str(content).strip()  # 去两边空格
                return content[:300]
        # 如果没有找到AI消息，返回空字符串
        return ""

    async def _extract_preferences(
        self, model: BaseChatModel, user_message: str, ai_summary: str | None = None
    ) -> Dict[str, Any]:
        """
        利用大语言模型提取用户在对话中表达的输出偏好
        args:
            model:大语言模型
            user_message:用户消息
            ai_summary:AI摘要
        return:
            preferences: {"preferred_output": ..., "preferred_chart_type": ..., "preferred_language": ...}
        """

        # 消防后勤场景输出偏好提取
        prompt = f"""从以下消防后勤对话中提取用户表达的个人输出偏好。

        规则：
        1. "preferred_output": 输出格式，仅允许 "table"(表格) / "chart"(图表) / "text"(纯文本)，未表达则取 None。
        2. "preferred_chart_type": 图表类型，如 "bar"(柱状图) / "line"(折线图) / "pie"(饼图)，未表达则取 None。
        3. "preferred_language": 回复语言，如 "zh"(中文) / "en"(英文)，未表达则取 None。

        用户消息：{user_message}

        AI回复摘要：{ai_summary}"""

        try:
            # 使用结构化输出，让模型严格按 MemoryEntities 返回
            structured_model = model.with_structured_output(MemoryEntities)
            response = await structured_model.ainvoke(prompt)
            if isinstance(response, MemoryEntities):
                return response.model_dump()
            if isinstance(response, dict):
                return {
                    "preferred_output": response.get("preferred_output"),
                    "preferred_chart_type": response.get("preferred_chart_type"),
                    "preferred_language": response.get("preferred_language"),
                }
        except Exception:
            logger.warning("MemoryUpdateMiddleware: LLM 提取失败，跳过本次更新", exc_info=True)

        return {"preferred_output": None, "preferred_chart_type": None, "preferred_language": None}


class MemoryUpdateMiddleware(AgentMiddleware):
    """
    人为干预，在agent回复后根据信息自动更新用户偏好
    """

    def __init__(self, model: BaseChatModel):
        self.model = model
        self.tools = MemoryUpdateMiddlewareTools()

    # 同步钩子，不执行操作
    def after_agent(self, state: AgentState[Any], runtime: Any) -> Dict[str, Any] | None:
        return None

    # 异步钩子
    async def aafter_agent(self, state: Dict[str, Any], runtime: Any) -> Dict[str, Any] | None:
        """
        Agent回复后触发，提取输出偏好并更新偏好文件
        args:
            state:
            runtime:
        """
        try:
            # 1.获取user_id
            ctx = getattr(runtime, "context", {})
            if not ctx:
                return None
            user_id = getattr(ctx, "user_id", None)
            if not user_id:
                return None

            # 2.获取消息列表
            messages: list[BaseMessage] = getattr(state, "messages", [])
            if not messages:
                return None

            # 3.判断是否需要更新
            user_messages = self.tools._is_meaningful_last(messages)
            if not user_messages:
                return None

            # 4.获取AI摘要
            ai_summary = self.tools._extract_ai_summary(messages)

            # 5.LLM提取输出偏好
            preferences = await self.tools._extract_preferences(self.model, user_messages, ai_summary)
            preferred_output = preferences.get("preferred_output")
            preferred_chart_type = preferences.get("preferred_chart_type")
            preferred_language = preferences.get("preferred_language")
            if not any([preferred_output, preferred_chart_type, preferred_language]):
                return None
            logger.info(
                f"已提取输出偏好，格式：{preferred_output}, "
                f"图表：{preferred_chart_type}, 语言：{preferred_language}"
            )

            # 6.从本地读取用户已有的偏好文件（不存在则视为首次对话）。
            existing_content = read_preferences(user_id)
            current_lines = existing_content.split("\n") if existing_content else []

            # 7.合并新偏好与旧偏好
            updated_content = self._merge_preferences(
                current_lines, preferred_output, preferred_chart_type, preferred_language
            )

            # 8.写回本地偏好文件
            write_preferences(user_id, updated_content)
            logger.info(
                f"已更新偏好，格式：{preferred_output}, "
                f"图表：{preferred_chart_type}, 语言：{preferred_language}"
            )
        except Exception as e:
            logger.warning(
                f"MemoryUpdateMiddleware: 更新失败，{e},跳过本次更新",
                exc_info=True,
            )

        return None

    def _merge_preferences(
        self,
        current_lines: list[str],
        preferred_output: str | None = None,
        preferred_chart_type: str | None = None,
        preferred_language: str | None = None,
    ) -> str:
        """
        将新的用户偏好合并至偏好文件
        策略：新值优先覆盖旧值；新值为空（None）时保留旧值。
        同时清理已废弃的 recent_equipment / recent_zones / recent_queries 区块（兼容旧文件迁移）。
        args:
            current_lines: 已有偏好文件行列表
            preferred_output: 新提取的输出格式偏好
            preferred_chart_type: 新提取的图表类型偏好
            preferred_language: 新提取的回复语言偏好
        """

        # 1.解析旧的偏好
        existing = {}
        for line in current_lines:
            stripped = line.strip()
            for key in ("preferred_output", "preferred_chart_type", "preferred_language"):
                if stripped.startswith(f"{key}:"):
                    val = stripped[len(key) + 1:].strip()
                    if val:
                        existing[key] = val

        # 2.合并：新值优先，无新值保留旧值
        merged: Dict[str, str] = {}
        new_values = {
            "preferred_output": preferred_output,
            "preferred_chart_type": preferred_chart_type,
            "preferred_language": preferred_language,
        }
        for key, new_val in new_values.items():
            val = (new_val or "").strip() if new_val else ""
            if not val:
                val = existing.get(key, "")
            if val:
                merged[key] = val

        # 3.从原内容中移除旧的 preferred_* 与已废弃的 recent_* 区块
        kept: list[str] = []
        i = 0
        while i < len(current_lines):
            stripped = current_lines[i].strip()
            is_preference_field = any(
                stripped.startswith(f"{p}:") for p in ("preferred_output", "preferred_chart_type", "preferred_language")
            )
            is_deprecated_recent = any(
                stripped.startswith(f"{r}:") for r in ("recent_equipment", "recent_zones", "recent_queries")
            )
            if is_preference_field or is_deprecated_recent:
                i += 1
                # 跳过区块内的缩进子行与空行
                while i < len(current_lines) and (not current_lines[i].strip() or current_lines[i].startswith(" ")):
                    i += 1
                continue
            kept.append(current_lines[i])
            i += 1

        # 4.追加合并后的偏好字段
        while kept and not kept[-1].strip():
            kept.pop()
        if kept:
            kept.append("")
        for key in ("preferred_output", "preferred_chart_type", "preferred_language"):
            if key in merged:
                kept.append(f"{key}: {merged[key]}")

        return "\n".join(kept).strip() + "\n"
