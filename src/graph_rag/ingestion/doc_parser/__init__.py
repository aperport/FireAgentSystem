"""
多模态文档解析子模块 — 将 PDF/Word/PNG/MD 等多种格式统一解析为结构化内容。

核心能力：
    将各类知识文档（法规PDF、操作手册Word、设备照片PNG、巡检报告MD等）
    解析为统一的中间格式，供后续切分、向量化、实体抽取使用。

支持的输入格式与解析引擎：

    | 格式    | 解析引擎           | 输出                         |
    |---------|--------------------|------------------------------|
    | PDF     | DotsOCR + VLLM     | Markdown + 图片提取          |
    | Word    | Unstructured       | Markdown + 嵌入图片提取      |
    | PNG/JPG | DotsOCR + VLLM     | 图片描述(Markdown)           |
    | HTML    | Unstructured       | Markdown                     |
    | MD      | 直接读取           | 原始Markdown                 |

子文件：
    - dispatcher.py      格式识别与引擎路由（根据文件类型选择解析引擎）
    - pdf_parser.py      PDF解析（扫描件OCR + 嵌入图片提取）
    - image_parser.py    图片解析（OCR + 多模态LLM生成描述）
    - office_parser.py   Word/HTML解析（Unstructured）
    - md_parser.py       Markdown直接读取（最简单，仅做标准化处理）

设计原则：
    1. 所有引擎输出统一格式（ParsedDocument），包含文本+图片+元数据
    2. 图片单独提取并生成文字描述，便于向量化入库
    3. 格式判断自动化，用户无需指定解析引擎

参考项目：Multimodal_RAG 的 dots_ocr/ 模块（PDF/图片 → Markdown）。
"""
