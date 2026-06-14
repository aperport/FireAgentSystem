"""
Office 文档解析模块 — 将 Word/HTML 文件解析为 Markdown + 提取嵌入图片。

解析引擎：Unstructured（开源文档解析库）

处理流程：
    1. 使用 Unstructured 解析文档结构（标题、段落、表格、图片）
    2. 将结构化内容转换为 Markdown 格式
    3. 提取嵌入图片 → 单独保存并标注在 Markdown 中的位置

支持的格式：
    - .docx / .doc — Word 文档（操作手册、巡检规范等）
    - .html / .htm — HTML 页面（系统帮助文档等）

Unstructured 优势：
    - 支持表格解析（消防手册中大量参数表格）
    - 自动识别文档层级（标题→章节→段落）
    - 提取嵌入媒体（图片、图表）

输出格式：
    ParsedDocument(text=Markdown内容, images=[{path, description}], metadata={...})
"""
