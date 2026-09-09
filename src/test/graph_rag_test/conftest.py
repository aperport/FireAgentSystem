"""
graph_rag 单元测试专用配置。

将项目 `src` 目录加入 sys.path，使测试可 `from graph_rag...` 导入被测模块。
仅对本目录（及子目录）的测试生效，不影响其他测试目录。
"""

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[2]
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))
