"""
多模态文档解析子模块 — 将各类文档统一解析为 ParsedDocument。

已实现：md_parser（Markdown 直接读取）
待实现：pdf_parser / image_parser / office_parser / dispatcher
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any


@dataclass
class ParsedDocument:
    """所有解析引擎的统一输出格式。

    Attributes:
        text: 解析后的文本内容（Markdown 格式）
        images: 提取的图片信息列表，每项包含 path 和 description
        metadata: 元数据字典，包含来源、格式、标题链等
    """
    text: str = ""
    images: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
