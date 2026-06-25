# logger.py
import logging
from logging.handlers import RotatingFileHandler

def get_logger(name=__name__, level=logging.INFO):
    """
    全局日志工具：一次配置，所有文件直接调用
    :param level: 设置默认输出的最底日志级别，默认为 INFO
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)  # 最低日志级别 (总开关)
    logger.handlers.clear()  # 防止重复打印

    # 日志格式（时间 + 文件名 + 行号 + 级别 + 信息）
    formatter = logging.Formatter(
        "%(asctime)s - %(filename)s - %(lineno)d - %(levelname)s - %(message)s"
    )

    # ===================== 输出到文件（自动生成 app.log）=====================
    # 自动分割日志，防止文件过大
    file_handler = RotatingFileHandler(
        "app.log",          # 日志自动保存在这个文件里
        maxBytes=10*1024*1024,  # 10M
        backupCount=5,
        encoding="utf-8"    # 解决中文乱码
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)

    # ===================== 输出到控制台 =====================
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)

    # 添加处理器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger