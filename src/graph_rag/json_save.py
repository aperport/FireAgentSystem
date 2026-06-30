"""
将信息保存的为工具，主要用于保存评估结果
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
    




        

        


