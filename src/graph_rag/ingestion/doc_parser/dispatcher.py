"""
格式识别与引擎路由 — 根据文件类型自动选择合适的解析引擎。

路由规则：
    | 文件后缀          | 选择引擎           |
    |------------------|--------------------|
    | .pdf             | pdf_parser         |
    | .png / .jpg / .jpeg / .bmp | image_parser  |
    | .docx / .doc     | office_parser      |
    | .html / .htm     | office_parser      |
    | .md / .markdown  | md_parser          |
    | 其他              | office_parser（兜底）|

对外接口：
    parse(file_path: str | Path) -> ParsedDocument

流程：
    1. 识别文件后缀
    2. 选择引擎并调用
    3. 返回统一的 ParsedDocument 对象

ParsedDocument 是所有解析引擎的统一输出格式（定义在 __init__.py 中），
包含 text、images、metadata 三个字段。
"""
