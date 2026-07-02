"""
Markdown 切分模块 — 将解析后的 Markdown 文本切分为适合入库的片段。

❌ 未实现（骨架）。上游输入：
    doc_parser 输出的 ParsedDocument（包含 text、images、metadata）

下游输出：
    1. 文本片段列表 → embedding.py → fire_doc_collection
    2. 图片文档列表 → embedding.py → fire_image_collection

切分策略（三步）：

    1. 标题切分（一级）
       按 Markdown 标题层级（# / ## / ###）将文档切成章节片段。
       每个片段保留当前标题，并继承父级标题链作为上下文。
       例如："消防法 > 第三章 > 第十五条" + 正文内容。

    2. 语义二次切分
       标题切分后，若某片段超过 max_chunk_size，按语义边界二次切分：
         - 优先在段落边界（\\n\\n）切
         - 其次在句子边界（。？！）切
       二次切分出的片段继承原片段的 title 与 header_chain。
       单片段不超过 max_chunk_size，不低于 min_chunk_size（避免碎片）。

    3. 图片提取与分离
       从文本中识别 ![alt](path) 标记，将图片信息单独提取：
         - 图片不走文本切分，整条写入 fire_image_collection
         - 图片的 text 用 alt 文本填充（后续由多模态模型增强）
         - 图片的 image_path 存原始路径
       图片从文本片段中可保留标记或移除，关键是图片信息单独成列表。

输出数据结构：

    文本片段 → langchain Document，metadata 包含：
        category      分类（regulation / standard / manual / faq），继承自 ParsedDocument
        source_file   来源文件 hash，继承自 ParsedDocument.metadata["parent_id"]
        source_name   来源文件名，继承自 ParsedDocument.metadata["filename"]
        title         当前片段标题（切分时确定）

    图片文档 → langchain Document，metadata 在文本片段基础上增加：
        image_path    图片原始路径（图片独有字段）

函数签名：

    split(parsed_doc: ParsedDocument,
          max_chunk_size: int = 512,
          min_chunk_size: int = 50) -> tuple[list[Document], list[Document]]

    Returns:
        (text_chunks, image_docs)
        text_chunks: 文本片段列表 → fire_doc_collection
        image_docs:  图片文档列表 → fire_image_collection

待实现：
    1. 标题切分：使用 MarkdownHeaderTextSplitter 或自定义正则按 #/##/### 切分
    2. 语义二次切分：超长片段按段落/句子边界切分，保留 header_chain
    3. 图片分离：提取 ![alt](path) 标记，生成图片 Document 列表
    4. 元数据继承：source_file / source_name / category / title 的正确传递
    5. 边界处理：min_chunk_size 以下的小片段合并到相邻片段

参考：doc_parser/example.py 中的 MarkdownHeaderTextSplitter 用法（食谱领域，可借鉴切分逻辑）
"""
