"""
Markdown 直接读取模块 — 最简单的解析器，仅做标准化处理。

处理流程：
    1. 读取 Markdown 文件内容
    2. 标准化处理：
        - 统一标题层级
        - 规范化图片引用语法（![alt](path) → 标准格式）
        - 识别并提取内嵌图片路径
    3. 返回 ParsedDocument

适用场景：
    - 已有的 Markdown 格式操作文档
    - 系统导出的巡检/值班报告（Markdown格式）
    - AGENTS.md 等纯文本文件

输出格式：
    ParsedDocument(text=原始Markdown, images=[], metadata={source_file, format})
"""
