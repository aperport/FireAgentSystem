"""
图片解析模块 — 将 PNG/JPG 等图片解析为文字描述（Markdown）。

处理流程：
    1. 图片预处理（尺寸调整、格式转换）
    2. OCR 文字识别（通过 DotsOCR 提取图中文字）
    3. 多模态 LLM 生成图片描述（用 qwen3-vl-plus 等多模态模型，
       生成一段自然语言描述，便于语义检索）

消防场景典型图片：
    - 设备照片：描述设备外观、型号标签、安装位置
    - 系统截图：描述界面布局、操作入口、按钮名称
    - 消防平面图：描述疏散通道、设备分布、分区标注

输出格式：
    ParsedDocument(text=描述内容, images=[{path, description}], metadata={...})

参考项目：Multimodal_RAG 的 dots_ocr/ 模块。
"""
