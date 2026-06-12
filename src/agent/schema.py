"""
自定义数据结构定义
包含运行时上下文文、用户偏好等类型定义
"""



from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional

from openai import BaseModel
from pydantic import Field


@dataclass   # dataclass自动定义__init__方法
class ProcurementContext:
    """
    定义用户信息
    运行时上下文，由调用方法在invoke时传入
    用于传递当前用户身份等基础信息
    """
    user_id: str                # 必填,用户唯一标识
    username: str               # 必填,用户名


@dataclass
class UserPreferences:
    """
    (此处后续可考虑使用图数据库和向量数据库存储)
    用户偏好数据结构，存储在长期记忆中，
    对应/memories/{user_id}/preferences.md 的内容。
    """
    preferred_output: str | None = None               # 'table' 或 'chart'
    preferred_chart_type: str | None = None           # 'bar', 'line', 'pie' 等
    preferred_currency: str | None = None             # 'CNY', 'USD' 等
    preferred_language: str | None = None             # 'zh', 'en' 等
    recent_suppliers: list[str] | None=None           # 近期使用的供应商列表
    recent_queries: list[str] | None=None             # 近期分析需求摘要列表

    def __post_init__(self):
        self.recent_suppliers = self.recent_suppliers or []
        self.recent_queries = self.recent_queries or []

class ChatRequest(BaseModel):
    """
    聊天请求数据结构
    """
    messages: str = Field(..., description="聊天内容")   # 必填（...标识）
    thread_id: str | None  = Field(None, description="聊天会话id")  # 可选，为空开启新会话（会话id）


class Message(BaseModel):
    """消息模型"""
    id: str = Field(..., description="消息唯一标识")
    role: str = Field(..., description="消息角色: user/assistant/tool")
    content: str = Field("", description="消息内容")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    tool_calls: Optional[list[Dict[str, Any]]] = Field(None, description="工具调用信息")
    tool_call_id: Optional[str] = Field(None, description="工具调用 ID")
    source: Optional[str] = Field(None, description="消息来源: main 或子代理名称")
    # 工具消息专属字段
    tool_name: Optional[str] = Field(None, description="工具名称")
    tool_status: Optional[str] = Field(None, description="工具状态: calling / done")
    text: Optional[str] = Field(None, description="工具结果文本")
    images: Optional[list[str]] = Field(None, description="工具结果图片列表")
    args: Optional[str] = Field(None, description="工具调用参数")

class ChatResponse(BaseModel):
    """对话响应模型"""
    thread_id: str = Field(..., description="会话 ID")
    messages: list[Message] = Field(default_factory=list, description="消息列表")

# 历史记录相关模型
# ============================================================

class Session(BaseModel):
    """会话模型"""
    thread_id: str = Field(..., description="会话 ID")
    title: str = Field(..., description="会话标题")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="最后更新时间")
    message_count: int = Field(0, description="消息数量")

class SessionListResponse(BaseModel):
    """会话列表响应模型"""
    sessions: list[Session] = Field(default_factory=list, description="会话列表")
    total: int = Field(0, description="总会话数")
    page: int = Field(1, description="当前页码")
    limit: int = Field(20, description="每页数量")


class SessionMessagesResponse(BaseModel):
    """会话消息历史响应模型"""
    thread_id: str = Field(..., description="会话 ID")
    messages: list[Message] = Field(default_factory=list, description="消息列表")


class DeleteSessionResponse(BaseModel):
    """删除会话响应模型"""
    success: bool = Field(True, description="是否成功")
    message: str = Field("会话已删除", description="响应消息")


# ============================================================
# SSE 流式事件模型
# ============================================================

class StreamTokenEvent(BaseModel):
    """Token 事件 - AI 生成的文本片段"""
    type: str = "token"
    content: str = Field(..., description="文本内容")
    source: str = Field("main", description="来源: main 或子代理名称")


class StreamToolStartEvent(BaseModel):
    """工具开始调用事件"""
    type: str = "tool_start"
    tool_call_id: str = Field(..., description="工具调用 ID")
    tool_name: str = Field(..., description="工具名称")
    source: str = Field("main", description="来源")


class StreamToolArgsEvent(BaseModel):
    """工具参数事件"""
    type: str = "tool_args"
    args: str = Field(..., description="工具参数字符串")


class StreamToolResultEvent(BaseModel):
    """工具执行结果事件"""
    type: str = "tool_result"
    tool_name: str = Field(..., description="工具名称")
    result: str = Field(..., description="执行结果")
    source: str = Field("main", description="来源")


class StreamDoneEvent(BaseModel):
    """流结束事件"""
    type: str = "done"
    thread_id: str = Field(..., description="会话 ID")
    content: str = Field("", description="完整回复内容")


class StreamErrorEvent(BaseModel):
    """错误事件"""
    type: str = "error"
    message: str = Field(..., description="错误信息")
