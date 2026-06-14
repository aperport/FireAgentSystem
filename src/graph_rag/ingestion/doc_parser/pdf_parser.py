"""
PDF 解析模块 — 将 PDF 文件解析为 Markdown + 提取嵌入图片。

两种 PDF 类型分别处理：
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
"""
