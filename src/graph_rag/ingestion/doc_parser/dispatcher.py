"""
格式识别与引擎路由 — 根据文件类型自动选择合适的解析引擎。

❌ 未实现（骨架）。路由规则：
    | 文件后缀          | 选择引擎           | 状态 |
    |------------------|--------------------|------|
    | .md / .markdown  | md_parser          | ✅   |
    | .pdf             | pdf_parser         | ❌   |
    | .png / .jpg / .jpeg / .bmp | image_parser  | ❌   |
    | .docx / .doc     | office_parser      | ❌   |
    | .html / .htm     | office_parser      | ❌   |
    | 其他              | office_parser（兜底）| ❌   |

对外接口：
    parse(file_path: str | Path) -> ParsedDocument

流程：
    1. 识别文件后缀
    2. 选择引擎并调用
    3. 返回统一的 ParsedDocument 对象

ParsedDocument 是所有解析引擎的统一输出格式（定义在 __init__.py 中），
包含 text、images、metadata 三个字段。

待实现：
    1. 文件后缀识别逻辑（os.path.splitext / Path.suffix）
    2. 引擎路由映射（后缀 → parser 实例）
    3. parse() 统一入口：识别后缀 → 调用对应 parser → 返回 ParsedDocument
    4. parse_directory() 目录批量解析：遍历文件 → 逐个 parse → 汇总结果
    5. 异常处理：不支持的格式给出友好提示
    6. 可扩展性：支持注册自定义解析器

依赖：
    - md_parser.py（✅ 已实现）
    - pdf_parser.py（❌ 待实现）
    - image_parser.py（❌ 待实现）
    - office_parser.py（❌ 待实现）
"""
