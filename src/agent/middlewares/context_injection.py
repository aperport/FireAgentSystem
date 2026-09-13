"""
上下文注入中间件 — 在 Agent 调用前将用户信息注入 SystemMessage。

Hook: before_agent / abefore_agent

功能：
    从 runtime.context 中获取 user_id / username 等信息，
    并主动读取本地偏好文件（data/memories/{user_id}/preferences.md），
    以 SystemMessage 的形式注入到对话中，供 Agent 了解用户偏好和权限。

注入内容：
    - 当前用户 user_id / username
    - 用户偏好文件路径: /memories/{user_id}/preferences.md
    - 用户偏好内容（主动读取，无需 Agent 再自行 read_file）

"""

from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage

from agent.memory.preferences_store import read_preferences
from util_tools.logger import get_logger

logger = get_logger(__name__)


class ContextInjectionMiddleware(AgentMiddleware):
    """上下文注入中间件，一般注入用户信息，用于后续区分识别用户偏好和权限"""

    def _build_notice(self, user_id: str, username: str) -> str:
        """
        组装注入的 SystemMessage 内容：用户基础信息 + 主动读取的偏好内容。
        """
        preferences = read_preferences(user_id).strip()
        if preferences:
            preference_section = preferences
        else:
            preference_section = "（暂无偏好记录，首次对话）"
        return (
            f"【系统上下文】\n"
            f"当前用户 user_id: {user_id}\n"
            f"当前用户 username: {username}\n"
            f"用户偏好文件路径: /memories/{user_id}/preferences.md\n"
            f"\n用户偏好内容：\n{preference_section}\n"
            f"\n（preferred_output, preferred_chart_type 和 preferred_language 由系统自动维护，你无需手动更新）"
        )

    def before_agent(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        """
        同步函数，从runtime.context中获取Id，usename等信息，
        并主动读取本地偏好内容，将用户信息注入到systemmessage信息中
        args:
            state : dict[str, Any]
            runtime : Any
        return:
            dict[str, Any]
        """
        # 从runtime.context中获取Id，usename等信息，没有返回空字典
        ctx = getattr(runtime, "context", {})
        if not ctx:
            logger.warning("上下文为空，跳过上下文注入")
            return None

        user_id = getattr(ctx, "user_id", None)
        if not user_id:
            logger.warning("user_id为空，跳过上下文注入")
            return None
        # 获取username，如果没有就使用userid作为name
        username = getattr(ctx, "username", None) or user_id
        logger.info(f"注入用户信息，user_id:{user_id},username:{username}")
        notice = self._build_notice(user_id, username)
        return {"messages": [SystemMessage(content=notice)]}

    async def abefore_agent(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        """
        异步函数，主动读取偏好内容并注入 systemmessage。
        本地偏好文件为小文件，读取为轻量同步 IO，直接复用同步逻辑；
        读取失败时由 read_preferences 内部兜底返回空字符串，不会中断对话。
        args:
            state : dict[str, Any]
            runtime : Any
        return:
            dict[str, Any]
        """
        return self.before_agent(state, runtime)
