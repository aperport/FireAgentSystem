"""
LLM 模型实例化 — 配置 DeepSeek 模型实例。

两个模型实例：
    DeepSeek_LLM     — 主模型，用于 Agent 推理和决策
    DeepSeek_FAST    — 快速模型，用于摘要、实体抽取等轻量任务

配置来源：env_utils.py 从 .env 加载
    DEEPSEEKAPI       — API Key
    DEEPSEEKURL       — API 地址
    DEEPSEEKMODEL     — 主模型名（如 deepseek-chat）
    DEEPSEEKMODELFAST — 快速模型名
"""
import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()


DeepSeek_API = os.getenv("DEEPSEEKAPI")
DeepSeek_URL = os.getenv("DEEPSEEKURL")
DeepSeek_MODEL = os.getenv("DEEPSEEKMODEL")
DeepSeek_MODEL_FAST = os.getenv("DEEPSEEKMODELFAST")


DeepSeek_LLM = ChatOpenAI(
    model=DeepSeek_MODEL,  # type: ignore
    api_key=DeepSeek_API,  # type: ignore
    base_url=DeepSeek_URL,
    timeout=60,
    temperature=0.7
)

DeepSeek_FAST = ChatOpenAI(
    model=DeepSeek_MODEL_FAST,  # type: ignore
    api_key=DeepSeek_API,  # type: ignore
    base_url=DeepSeek_URL,
    timeout=60,
    temperature=0.7,
    # DeepSeek JSON Output 模式：强制返回 JSON 格式
    # 配合 prompt 中的 json 样例使用
    model_kwargs={"response_format": {"type": "json_object"}},
)