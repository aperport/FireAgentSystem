"""
上下文注入中间件 — 在 Agent 调用前将用户信息注入 SystemMessage。

Hook: before_agent / abefore_agent

功能：
    从 runtime.context 中获取 user_id / username 等信息，
    以 SystemMessage 的形式注入到对话中，供 Agent 读取用户偏好和权限。

注入内容：
    - 当前用户 user_id / username
    - 用户偏好文件路径: /memories/{user_id}/preferences.md
    - 提示 Agent 优先读取偏好文件了解用户习惯

消防场景适配（相较于原采购项目）：
    - 上下文类从 ProcurementContext 改为 FireLogisticsContext
    - 去掉 preferred_currency（消防场景无货币偏好）
    - 偏好文件中 recent_suppliers 改为 recent_equipment
"""

from typing import Any, Optional

from unitl_tools.logger import get_logger
from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import SystemMessage

logger = get_logger(__name__)


class ContextInjectionMiddleware(AgentMiddleware):
    def before_agent(self,state : dict[str, Any],runtime:Any) -> dict[str, Any] | None:
        """
        同步函数，将用户信息注入到systemmessage信息中
        args:
            state : dict[str, Any]
            runtime : Any
        return:
            dict[str, Any]
        """ 
        # 从runtime.context中获取Id，usename等信息，没有返回空字典
        ctx = getattr(runtime,"context",{})
        """
        与上文等价
        try:
            ctx = runtime.context
        except AttributeError:
            ctx = {}
        """
        if not ctx:
            logger.warning("context is empty, skip context injection")
            return None
        
        user_id = getattr(ctx, "user_id", None)
        if not user_id:
            logger.warning("user_id is empty, skip context injection")
            return None
        # 获取username，如果没有就使用userid作为name
        username = getattr(ctx, "username", None) or user_id
        logger.info(f"注入用户信息，user_id:{user_id},username:{username}")
        notice = (
            f"【系统上下文】\n"
            f"当前用户 user_id: {user_id}\n"
            f"当前用户 username: {username}\n"
            f"用户偏好文件路径: /memories/{user_id}/preferences.md\n"
            f"\n请首先使用 read_file 读取上述偏好文件了解用户偏好。"
            f"\n（recent_equipment, recent_zones 和 recent_queries 由系统自动维护，你无需手动更新）"
        )
        return {"messages":[SystemMessage(content=notice)]}

    async def abefore_agent(self,state : dict[str, Any],runtime:Any) -> dict[str, Any] | None:
        """
        同函数的异步函数，将用户信息注入到systemmessage信息中，底层逻辑不涉及IO可以直接同步调用
        args:
            state : dict[str, Any]
            runtime : Any
        return:
            dict[str, Any]
        """
        return  self.before_agent(state,runtime)