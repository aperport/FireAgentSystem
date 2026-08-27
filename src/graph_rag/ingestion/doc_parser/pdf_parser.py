"""
PDF 解析模块 — 将 PDF 文件解析为 Markdown + 提取嵌入图片。

❌ 未实现（骨架）。两种 PDF 类型分别处理：
    1. 文字型 PDF（有文本层的电子文档）：
        - 直接提取文本内容 → Markdown
        - 提取嵌入图片 → 单独保存并标注位置

    2. 扫描件 PDF（纯图片，无文本层）：
        - 通过 DotsOCR (VLLM) 进行 OCR 识别 → Markdown
        - 同时提取页面图片 → 单独保存

解析引擎配置：
    DotsOCR 服务地址从 graph_rag/config.py 的 DOTS_OCR_URL 读取。
    VLLM 推理客户端负责 OCR 和文档理解。

参考项目：Multimodal_RAG 的 dots_ocr/parser.py。

待实现：
    1. PDF 类型检测：判断是文字型还是扫描件（检查文本层是否有内容）
    2. 文字型 PDF 解析：PyMuPDF / pdfplumber 提取文本和图片
    3. 扫描件 PDF 解析：DotsOCR 逐页 OCR + VLLM 文档理解
    4. 嵌入图片提取：从 PDF 中提取嵌入的图片对象
    5. 页面 → Markdown 转换：保留标题层级、表格结构
    6. 元数据构建：页数、文件大小、是否扫描件等

依赖：
    - DotsOCR 服务（配置地址从 config.py 读取）
    - PyMuPDF / pdfplumber（文字型 PDF 文本提取）
    - ParsedDocument 数据类（from . import ParsedDocument）
"""
import pdf_inspector
from markitdown import MarkItDown


class WordPdfTransformer:
    def __init__(self):
        self.md_parser = MarkItDown()


class ScanPdfTransformer:
    def __init__(self):
        self.md_parser = MarkItDown()
