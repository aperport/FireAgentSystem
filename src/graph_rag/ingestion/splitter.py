"""
Markdown 切分模块 — 将解析后的 Markdown 文本切分为适合入库的片段。

✅ 已实现。上游输入：
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

已实现：
    1. 标题切分：使用 MarkdownHeaderTextSplitter 按 #/##/### 切分
    2. 语义二次切分：超长片段按段落/句子边界切分，保留 header_chain
    3. 图片分离：提取 ![alt](path) 标记，生成图片 Document 列表
    4. 元数据继承：source_file / source_name / category / title 的正确传递
    5. 边界处理：min_chunk_size 以下的小片段合并到相邻片段

参考：doc_parser/example.py 中的 MarkdownHeaderTextSplitter 用法（食谱领域，可借鉴切分逻辑）
"""

import re
import uuid
from typing import List, Dict, Any, Tuple

from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.documents import Document

from .doc_parser import ParsedDocument
from util_tools.logger import get_logger

logger = get_logger(__name__)

# ===================== 图片提取正则 =====================
# 匹配 ![alt](path) 和 ![alt](path "title") 两种格式
_IMAGE_PATTERN = re.compile(
    r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)"
)

# 句子边界正则：中文句号、问号、叹号，以及英文句末标点
_SENTENCE_BOUNDARY = re.compile(r"(?<=[。？！.!?])\s*")


def split(
    parsed_doc: ParsedDocument,
    max_chunk_size: int = 512,
    min_chunk_size: int = 50,
) -> Tuple[List[Document], List[Document]]:
    """将 ParsedDocument 切分为文本片段和图片文档。

    三步切分流程：
        1. 标题切分 — 按 Markdown 标题层级拆分章节
        2. 语义二次切分 — 超长片段按段落/句子边界再切
        3. 图片分离 — 提取图片标记，生成独立的图片 Document

    Args:
        parsed_doc: doc_parser 输出的解析文档
        max_chunk_size: 单片段最大字符数，超过则二次切分。默认 512
        min_chunk_size: 单片段最小字符数，低于此值会合并到相邻片段。默认 50

    Returns:
        (text_chunks, image_docs) 二元组
        - text_chunks: 文本片段列表，每个是 langchain Document
        - image_docs: 图片文档列表，每个是 langchain Document
    """
    # ---- 第 3 步先做：从文本中提取图片，生成图片 Document ----
    image_docs = _extract_image_docs(parsed_doc)

    # ---- 第 1 步：标题切分 ----
    header_chunks = _split_by_headers(parsed_doc)

    # ---- 第 2 步：语义二次切分（处理超长片段） ----
    text_chunks = _semantic_resplit(header_chunks, max_chunk_size)

    # ---- 边界处理：合并过小的片段 ----
    text_chunks = _merge_small_chunks(text_chunks, min_chunk_size)

    # ---- 补充元数据：为每个片段添加 chunk_id 和 chunk_index ----
    for i, chunk in enumerate(text_chunks):
        chunk.metadata["chunk_id"] = str(uuid.uuid4())
        chunk.metadata["chunk_index"] = i

    logger.info(
        f"切分完成: source_name={parsed_doc.metadata.get('filename', '未知')}, "
        f"文本片段={len(text_chunks)}, 图片文档={len(image_docs)}"
    )
    return text_chunks, image_docs


# ===================== 第 1 步：标题切分 =====================

def _split_by_headers(parsed_doc: ParsedDocument) -> List[Document]:
    """按 Markdown 标题层级切分文档为章节片段。

    使用 langchain 的 MarkdownHeaderTextSplitter，按 # / ## / ### 三级标题切分。
    每个片段保留标题文本，并继承父级标题链作为上下文。

    Args:
        parsed_doc: 解析后的文档

    Returns:
        按标题切分后的 Document 列表，每个片段的 metadata 包含
        title（当前标题）和 header_chain（标题链）
    """
    # 定义要切分的标题层级
    # 键是 Markdown 标记，值是 metadata 中存储该级标题的 key
    headers_to_split_on = [
        ("#", "h1_title"),       # 一级标题 → 如 "消防法"
        ("##", "h2_title"),      # 二级标题 → 如 "第三章"
        ("###", "h3_title"),     # 三级标题 → 如 "第十五条"
    ]

    # 创建 Markdown 标题切分器
    # strip_headers=False：保留标题文本在片段内容中，便于理解上下文
    markdown_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=headers_to_split_on,
        strip_headers=False,
    )

    try:
        # 执行标题切分，返回 langchain Document 列表
        # 每个 Document 的 metadata 自动包含 h1_title / h2_title / h3_title
        raw_chunks = markdown_splitter.split_text(parsed_doc.text)
    except Exception as e:
        # 切分失败时，将整个文档作为单个片段返回，避免数据丢失
        logger.warning(f"标题切分失败，回退为整文档: {e}")
        return [_build_single_chunk(parsed_doc)]

    # 如果切分结果为空（如文档无标题），也回退为整文档
    if not raw_chunks:
        return [_build_single_chunk(parsed_doc)]

    # 为每个片段补充元数据：title、header_chain、以及从 ParsedDocument 继承的字段
    chunks = []
    for chunk in raw_chunks:
        # 构建标题链：从 h1 > h2 > h3 逐级拼接
        # 例如 "消防法 > 第三章 > 第十五条"
        header_chain_parts = []
        for _, meta_key in headers_to_split_on:
            header_val = chunk.metadata.get(meta_key)
            if header_val:
                header_chain_parts.append(str(header_val))

        header_chain = " > ".join(header_chain_parts) if header_chain_parts else ""

        # 当前片段标题：取最深层级的标题
        # 例如 h3 存在则用 h3，否则用 h2，再否则用 h1
        title = ""
        for _, meta_key in reversed(headers_to_split_on):
            if chunk.metadata.get(meta_key):
                title = str(chunk.metadata[meta_key])
                break

        # 继承 ParsedDocument 的元数据字段
        # source_file: 来源文件 hash（即 parent_id）
        # source_name: 来源文件名
        # category: 文档分类
        chunk.metadata["source_file"] = parsed_doc.metadata.get("parent_id", "")
        chunk.metadata["source_name"] = parsed_doc.metadata.get("filename", "")
        chunk.metadata["category"] = parsed_doc.metadata.get("category", "")
        chunk.metadata["title"] = title
        chunk.metadata["header_chain"] = header_chain

        # 清理 MarkdownHeaderTextSplitter 自动添加的中间 key（h1_title 等）
        # 这些信息已整合到 title 和 header_chain，不再单独保留
        for _, meta_key in headers_to_split_on:
            chunk.metadata.pop(meta_key, None)

        chunks.append(chunk)

    logger.debug(f"标题切分: 生成 {len(chunks)} 个章节片段")
    return chunks


def _build_single_chunk(parsed_doc: ParsedDocument) -> Document:
    """当标题切分失败或文档无标题时，将整个文档包装为单个片段。

    Args:
        parsed_doc: 解析后的文档

    Returns:
        包含完整文档内容的单个 Document
    """
    # 尝试从原文提取一级标题作为 title
    title = ""
    for line in parsed_doc.text.split("\n"):
        match = re.match(r"^#\s+(.+)$", line)
        if match:
            title = match.group(1).strip()
            break

    return Document(
        page_content=parsed_doc.text,
        metadata={
            "source_file": parsed_doc.metadata.get("parent_id", ""),
            "source_name": parsed_doc.metadata.get("filename", ""),
            "category": parsed_doc.metadata.get("category", ""),
            "title": title,
            "header_chain": title,  # 无子标题时，header_chain 等于 title
        },
    )


# ===================== 第 2 步：语义二次切分 =====================

def _semantic_resplit(
    chunks: List[Document], max_chunk_size: int
) -> List[Document]:
    """对超长片段进行语义二次切分。

    切分优先级：
        1. 段落边界（\\n\\n）— 语义最完整的切分点
        2. 句子边界（。？！）— 段落内仍超长时的后备切分点

    二次切分出的每个片段继承原片段的 title 和 header_chain。

    Args:
        chunks: 标题切分后的片段列表
        max_chunk_size: 单片段最大字符数

    Returns:
        二次切分后的片段列表（未超长的片段原样保留）
    """
    result = []

    for chunk in chunks:
        content = chunk.page_content

        # 片段未超长，直接保留
        if len(content) <= max_chunk_size:
            result.append(chunk)
            continue

        # 片段超长，需要二次切分
        sub_chunks = _split_long_chunk(content, max_chunk_size)

        # 每个子片段继承原片段的元数据
        for sub_content in sub_chunks:
            # 复制原 metadata，避免修改原对象
            sub_metadata = dict(chunk.metadata)
            result.append(Document(
                page_content=sub_content,
                metadata=sub_metadata,
            ))

        logger.debug(
            f"二次切分: '{chunk.metadata.get('title', '无标题')}' "
            f"({len(content)}字 → {len(sub_chunks)}个片段)"
        )

    return result


def _split_long_chunk(text: str, max_size: int) -> List[str]:
    """将超长文本按语义边界切分为多个子片段。

    切分策略：
        1. 先按段落边界（双换行 \\n\\n）切分
        2. 如果某段落仍超长，按句子边界（。？！）切分
        3. 如果某句子仍超长（极端情况），强制按 max_size 截断

    Args:
        text: 待切分的文本
        max_size: 每个片段的最大字符数

    Returns:
        切分后的文本片段列表
    """
    # ---- 第 1 轮：按段落边界切分 ----
    # 按双换行拆分段落，保留段落间的分隔符以便后续拼接
    paragraphs = text.split("\n\n")

    # 将段落重新组合，使每个片段不超过 max_size
    # 策略：逐段累加，超长则切出当前片段
    fragments: List[str] = []
    current = ""

    for para in paragraphs:
        # 尝试将当前段落追加到正在构建的片段
        candidate = current + ("\n\n" if current else "") + para

        if len(candidate) <= max_size:
            # 未超长，继续累加
            current = candidate
        else:
            # 超长了：先把当前已累加的内容保存为一个片段
            if current:
                fragments.append(current)

            # 检查单独这个段落是否也超长
            if len(para) > max_size:
                # ---- 第 2 轮：按句子边界切分超长段落 ----
                sub_fragments = _split_by_sentences(para, max_size)
                fragments.extend(sub_fragments)
                current = ""  # 重置累加器
            else:
                # 段落本身不超长，作为新片段的起始
                current = para

    # 别忘了最后一段累加内容
    if current:
        fragments.append(current)

    return fragments if fragments else [text]


def _split_by_sentences(text: str, max_size: int) -> List[str]:
    """按句子边界切分超长段落。

    在中文句号、问号、叹号处切分。如果单个句子仍超长（极端情况），
    则强制按 max_size 字符截断。

    Args:
        text: 待切分的段落文本
        max_size: 每个片段的最大字符数

    Returns:
        切分后的文本片段列表
    """
    # 按句子边界拆分，保留标点符号（lookbehind 不断行）
    # _SENTENCE_BOUNDARY 匹配 "。？！.!? " 后面的位置
    sentences = _SENTENCE_BOUNDARY.split(text)

    # 过滤空字符串
    sentences = [s for s in sentences if s.strip()]

    if not sentences:
        return [text]

    # 将句子重新组合，使每个片段不超过 max_size
    fragments: List[str] = []
    current = ""

    for sentence in sentences:
        candidate = current + sentence

        if len(candidate) <= max_size:
            current = candidate
        else:
            # 保存当前累加内容
            if current:
                fragments.append(current)

            # 极端情况：单个句子超过 max_size，强制截断
            if len(sentence) > max_size:
                for i in range(0, len(sentence), max_size):
                    fragments.append(sentence[i : i + max_size])
                current = ""
            else:
                current = sentence

    # 最后一部分
    if current:
        fragments.append(current)

    return fragments if fragments else [text]


# ===================== 第 3 步：图片提取与分离 =====================

def _extract_image_docs(parsed_doc: ParsedDocument) -> List[Document]:
    """从 ParsedDocument 中提取图片信息，生成独立的图片 Document 列表。

    图片不走文本切分流程，而是整条写入 fire_image_collection。
    图片 Document 的 page_content 用 alt 文本填充（后续由多模态模型增强），
    metadata 中额外包含 image_path 字段。

    Args:
        parsed_doc: 解析后的文档（其 images 字段已由 md_parser 提取）

    Returns:
        图片 Document 列表
    """
    image_docs = []

    for img_info in parsed_doc.images:
        # img_info 是 md_parser._extract_images() 返回的字典
        # 格式: {"path": "images/xxx.png", "alt": "消防设备示意图"}
        image_path = img_info.get("path", "")
        alt_text = img_info.get("alt", "")

        # 图片 Document 的 page_content 用 alt 文本填充
        # 后续由多模态 embedding 模型增强描述
        image_doc = Document(
            page_content=alt_text,
            metadata={
                # 继承 ParsedDocument 的元数据
                "source_file": parsed_doc.metadata.get("parent_id", ""),
                "source_name": parsed_doc.metadata.get("filename", ""),
                "category": parsed_doc.metadata.get("category", ""),
                "title": alt_text or "图片",  # 无 alt 时用 "图片" 兜底
                # 图片独有字段：原始路径
                "image_path": image_path,
            },
        )
        image_docs.append(image_doc)

    logger.debug(f"图片分离: 提取 {len(image_docs)} 张图片")
    return image_docs


# ===================== 边界处理：合并过小片段 =====================

def _merge_small_chunks(
    chunks: List[Document], min_chunk_size: int
) -> List[Document]:
    """合并字符数低于 min_chunk_size 的小片段到相邻片段，避免碎片。

    合并策略：
        - 优先向后合并（与下一个片段拼接）
        - 如果是最后一个片段，则向前合并（与前一个片段拼接）
        - 合并时用双换行分隔，保持段落结构

    Args:
        chunks: 待处理的片段列表
        min_chunk_size: 最小片段字符数，低于此值触发合并

    Returns:
        合并后的片段列表
    """
    if not chunks or min_chunk_size <= 0:
        return chunks

    # 先标记哪些片段需要合并，避免边遍历边修改
    merged = list(chunks)  # 浅拷贝，不修改原列表
    i = 0

    while i < len(merged):
        # 当前片段过小，需要合并
        if len(merged[i].page_content) < min_chunk_size:
            # 优先向后合并：与下一个片段拼接
            if i + 1 < len(merged):
                merged[i] = _concat_docs(merged[i], merged[i + 1])
                # 删除被合并的下一个片段
                merged.pop(i + 1)
                # 不递增 i，继续检查合并后的片段是否仍过小
                continue

            # 如果是最后一个片段，向前合并：与前一个片段拼接
            elif i - 1 >= 0:
                merged[i - 1] = _concat_docs(merged[i - 1], merged[i])
                merged.pop(i)
                # 合并完成，退出循环（已无后续片段可合并）
                break

            # 孤立片段（列表中只有一个且过小），保留不处理
            else:
                i += 1
        else:
            i += 1

    if len(merged) < len(chunks):
        logger.debug(
            f"小片段合并: {len(chunks)} → {len(merged)} 个片段 "
            f"(min_chunk_size={min_chunk_size})"
        )

    return merged


def _concat_docs(doc_a: Document, doc_b: Document) -> Document:
    """将两个 Document 拼接为一个，内容用双换行分隔，元数据取前者。

    拼接后的片段继承 doc_a 的元数据（title、header_chain 等），
    因为 doc_a 在文档中的位置更靠前，其标题链更具代表性。

    Args:
        doc_a: 前一个 Document
        doc_b: 后一个 Document

    Returns:
        拼接后的新 Document
    """
    return Document(
        page_content=doc_a.page_content + "\n\n" + doc_b.page_content,
        metadata=dict(doc_a.metadata),  # 继承前者的元数据
    )
