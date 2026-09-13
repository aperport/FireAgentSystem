"""
本地用户偏好存储模块 — 用户偏好文件的读写（本地文件系统）。

设计目的：
    替代原 StoreBackend / Postgres 存储，将用户偏好直接持久化到本地磁盘，
    路径约定为：data/memories/{user_id}/preferences.md。

对外接口：
    read_preferences(user_id)  -> str   # 读取偏好文本，不存在返回空字符串
    write_preferences(user_id, content) -> None  # 写入偏好文本，自动创建目录
"""

from pathlib import Path

from agent.config import LOCAL_MEMORY_DIR


def get_preferences_path(user_id: str) -> Path:
    """返回指定用户的偏好文件路径（data/memories/{user_id}/preferences.md）。"""
    return LOCAL_MEMORY_DIR / str(user_id) / "preferences.md"


def read_preferences(user_id: str) -> str:
    """读取用户偏好文件内容，文件不存在或读取失败时返回空字符串。"""
    path = get_preferences_path(user_id)
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return ""


def write_preferences(user_id: str, content: str) -> None:
    """写入用户偏好文件，自动创建父目录。"""
    path = get_preferences_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
