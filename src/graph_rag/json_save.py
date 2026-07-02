"""
JSON 持久化工具 — 异步安全地读写 JSON 文件，主要用于保存检索结果和评估数据。

✅ 已实现。提供三个异步方法：
    - save_json()         覆盖写入 JSON（全量保存）
    - load_json()         读取 JSON 文件
    - append_json_item()  追加写入 JSON 数组（按日期分文件）

线程安全：使用 asyncio.Lock 保证并发写入安全。
文件命名：自动按日期命名（如 T20260702.json），append 时按 file_name + 日期拼接。

⚠️ 已知问题：
    1. FILE_LOCK 是模块级全局锁，多实例场景下无法跨进程保护
    2. append_json_item() 中 except 裸捕获，应改为 except (FileNotFoundError, json.JSONDecodeError)
    3. 路径拼接使用字符串 + 而非 os.path.join，不同操作系统可能出问题
    4. get_today_date() 函数仅被间接使用，可内联或移除

待优化：
    - 使用 pathlib.Path 统一路径操作
    - 细化异常捕获，避免静默吞掉非预期错误
    - 支持自定义文件滚动策略（按大小/按天数）
"""

import asyncio
from typing import Any

import aiofiles
from util_tools.logger import get_logger
from datetime import datetime
import json
import os


FILE_LOCK = asyncio.Lock()
logger = get_logger(__name__)

def get_today_date() -> str:
    """
    获取当前日期,格式为年月日。
    :return: 当前日期处理后的名称
    """
    today = datetime.now()
    sep = ""
    date_str = today.strftime(f"%Y{sep}%m{sep}%d")
    return date_str + ".json"




async def save_json(data:Any, dir_name: str|None = None, file_name: str|None = None) -> None:
    """
    将数据保存为json,覆盖写入。
    args:
        data: 需要保存的数据
        dir_name: 文件夹
        file_name: 文件名
    returns:
        None
    """
    today = datetime.now()
    sep = ""
    if file_name :
        date_str = file_name + today.strftime(f"%Y{sep}%m{sep}%d") + ".json"
    else:
        date_str = today.strftime(f"%Y{sep}%m{sep}%d") + ".json"
    
    if dir_name:
        file_path = dir_name + date_str
    else:
        file_path = "./data/" + date_str

    async with FILE_LOCK:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        json_str = json.dumps(data, ensure_ascii=False, indent=4)
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f: 
            await f.write(json_str)




async def load_json(file_path: str) -> Any:
    """
    加载数据
    args:
        file_path: 文件路径
    returns:
        Any
    """
    async with FILE_LOCK:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            json_str = await f.read()
            return json.loads(json_str)
        



async def append_json_item(dir_name: str, item: Any, file_name: str) -> None:
    """
    追加数据
    args:
        dir_name: 文件夹
        item: 需要追加的数据
        file_name: 文件名
    returns:
        None
    """
    today = datetime.now()
    sep = ""
    if file_name :
        date_str = file_name + today.strftime(f"%Y{sep}%m{sep}%d") + ".json"
    else:
        date_str = today.strftime(f"%Y{sep}%m{sep}%d") + ".json"
    
    if dir_name:
        file_path = dir_name + date_str
    else:
        file_path = "./data/" + date_str

    async with FILE_LOCK:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        try:
            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                json_str = await f.read()
                data = json.loads(json_str)
        except:
            data = []
        data.append(item)
        json_str = json.dumps(data, ensure_ascii=False, indent=4)
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f: 
            await f.write(json_str)
    




        

        


