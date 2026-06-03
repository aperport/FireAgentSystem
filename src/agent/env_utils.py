"""此处是一些配置信息"""
from dotenv import load_dotenv
import os
load_dotenv (override=True)

DeepSeek_API = os.getenv("DEEPSEEKAPI")
DeepSeek_URL = os.getenv("DEEPSEEKURL")
DeepSeek_MODEL = os.getenv("DEEPSEEKMODEL")
DeepSeek_MODEL_FAST = os.getenv("DEEPSEEKMODELFAST")
