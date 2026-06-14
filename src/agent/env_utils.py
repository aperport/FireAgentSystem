"""
环境变量加载模块 — 从 .env 文件加载所有配置到 os.environ。

加载的环境变量：
    LLM 相关：
        DEEPSEEKAPI       — DeepSeek API Key
        DEEPSEEKURL       — DeepSeek API 地址
        DEEPSEEKMODEL     — 主模型名
        DEEPSEEKMODELFAST — 快速模型名

    GraphRAG 相关（新增）：
        NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD     — Neo4j 连接
        MILVUS_HOST / MILVUS_PORT                     — Milvus 连接
        DASHSCOPE_API_KEY                              — DashScope Embedding
        DOTS_OCR_URL                                   — DotsOCR 服务地址

    后端相关：
        JAVA_API_BASE_URL  — Java后端API地址
        MCP_SERVER_URL     — MCP Server地址
        MONGODB_URI        — MongoDB连接
        APP_ENV            — 运行环境 (development/production)

使用方式：
    from agent.env_utils import DeepSeek_API, Neo4j_URI, ...
"""
from dotenv import load_dotenv
import os
load_dotenv (override=True)

DeepSeek_API = os.getenv("DEEPSEEKAPI")
DeepSeek_URL = os.getenv("DEEPSEEKURL")
DeepSeek_MODEL = os.getenv("DEEPSEEKMODEL")
DeepSeek_MODEL_FAST = os.getenv("DEEPSEEKMODELFAST")
