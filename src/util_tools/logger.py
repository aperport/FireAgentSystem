# logger.py
# [简化理由] 原先使用标准库 logging + RotatingFileHandler 手动配置，
# 但 loguru 已在 requirements.txt 中，功能更完善（自动轮转、彩色输出、异常追踪）。
# 现改为直接代理 loguru，保持 get_logger(name) 接口不变，所有调用方无需修改。
from loguru import logger

def get_logger(name: str = __name__):
    """获取 logger 实例（代理 loguru，保持接口兼容）。

    Args:
        name: 模块名（loguru 默认不使用 name 分层，此处仅作标记）
    """
    return logger.bind(name=name)
