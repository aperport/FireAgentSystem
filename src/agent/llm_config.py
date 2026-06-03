"""此处是创建的llm模型"""
from langchain_openai import ChatOpenAI

from agent.env_utils import DeepSeek_API, DeepSeek_MODEL, DeepSeek_URL

DeepSeek_LLM = ChatOpenAI(
    model=DeepSeek_MODEL, # type: ignore
    api_key=DeepSeek_API, # type: ignore
    base_url=DeepSeek_URL,
    timeout=60,
    temperature=0.7
)