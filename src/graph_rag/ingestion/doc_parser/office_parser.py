"""
Office 文档解析模块 — 将 Word/HTML 文件解析为 Markdown + 提取嵌入图片。

❌ 未实现（骨架）。解析引擎：Unstructured（开源文档解析库）

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

待实现：
    1. Unstructured 集成：调用 partition_docx / partition_html 解析文档
    2. 结构化 → Markdown 转换：将 Unstructured 的 Element 列表转为 Markdown
    3. 表格处理：Unstructured 的 TableElement → Markdown 表格
    4. 嵌入图片提取：从 docx 中提取 media/ 目录下的图片文件
    5. 元数据构建：来源文件、格式、标题链等

依赖：
    - unstructured 库（pip install unstructured[docx,html]）
    - ParsedDocument 数据类（from . import ParsedDocument）
"""
