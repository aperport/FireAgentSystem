"""
多模态文档解析子模块 — 将 PDF/Word/PNG/MD 等多种格式统一解析为结构化内容。

核心能力：
    将各类知识文档（法规PDF、操作手册Word、设备照片PNG、巡检报告MD等）
    解析为统一的中间格式，供后续切分、向量化、实体抽取使用。

支持的输入格式与解析引擎：

    | 格式    | 解析引擎           | 状态 | 输出                         |
    |---------|--------------------|------|------------------------------|
    | MD      | 直接读取           | ✅   | 原始Markdown + 图片提取      |
    | PDF     | DotsOCR + VLLM     | ❌   | Markdown + 图片提取          |
    | Word    | Unstructured       | ❌   | Markdown + 嵌入图片提取      |
    | HTML    | Unstructured       | ❌   | Markdown                     |
    | PNG/JPG | DotsOCR + VLLM     | ❌   | 图片描述(Markdown)           |

子文件：
    - dispatcher.py      格式识别与引擎路由（❌ 骨架）
    - pdf_parser.py      PDF解析（❌ 骨架：扫描件OCR + 嵌入图片提取）
    - image_parser.py    图片解析（❌ 骨架：OCR + 多模态LLM生成描述）
    - office_parser.py   Word/HTML解析（❌ 骨架：Unstructured）
    - md_parser.py       Markdown直接读取（✅ 已实现：标准化+元数据增强+图片提取）
    - example.py         数据准备模块（⚠️ 已实现但属于食谱领域，与消防场景无关）

设计原则：
    1. 所有引擎输出统一格式（ParsedDocument），包含文本+图片+元数据
    2. 图片单独提取并生成文字描述，便于向量化入库
    3. 格式判断自动化，用户无需指定解析引擎

参考项目：Multimodal_RAG 的 dots_ocr/ 模块（PDF/图片 → Markdown）。
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
    
