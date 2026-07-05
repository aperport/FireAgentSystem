"""
Markdown 切分模块 — 将 ParsedDocument 切分为文本片段和图片文档。

三步切分：标题切分 → 语义二次切分 → 图片分离。
输出：(text_chunks, image_docs)，均为 langchain Document。
"""

import re
import uuid
from typing import List, Tuple

from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain_core.documents import Document

from .doc_parser import ParsedDocument
from util_tools.logger import get_logger

logger = get_logger(__name__)

_HEADERS = [("#", "h1_title"), ("##", "h2_title"), ("###", "h3_title")]
_SENTENCE_BOUNDARY = re.compile(r"(?<=[。？！.!?])\s*")


def split(
    parsed_doc: ParsedDocument,
    max_chunk_size: int = 512,
    min_chunk_size: int = 50,
) -> Tuple[List[Document], List[Document]]:
    """将 ParsedDocument 切分为 (text_chunks, image_docs)。"""
    image_docs = _extract_image_docs(parsed_doc)
    header_chunks = _split_by_headers(parsed_doc)
    text_chunks = _resplit_long(header_chunks, max_chunk_size)
    text_chunks = _merge_small(text_chunks, min_chunk_size)

    for i, chunk in enumerate(text_chunks):
        chunk.metadata["chunk_id"] = str(uuid.uuid4())
        chunk.metadata["chunk_index"] = i

    logger.info(
        f"切分完成: {parsed_doc.metadata.get('filename', '未知')}, "
        f"文本={len(text_chunks)}, 图片={len(image_docs)}"
    )
    return text_chunks, image_docs


# ===================== 标题切分 =====================

def _split_by_headers(parsed_doc: ParsedDocument) -> List[Document]:
    """按 #/##/### 切分，每个片段继承标题链上下文。"""
    splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=_HEADERS, strip_headers=False,
    )
    try:
        raw_chunks = splitter.split_text(parsed_doc.text)
    except Exception as e:
        logger.warning(f"标题切分失败，回退为整文档: {e}")
        raw_chunks = []

    if not raw_chunks:
        # 回退：整文档包装为单个片段
        title = ""
        for line in parsed_doc.text.split("\n"):
            m = re.match(r"^#\s+(.+)$", line)
            if m:
                title = m.group(1).strip()
                break
        return [Document(
            page_content=parsed_doc.text,
            metadata=_base_meta(parsed_doc, title=title, header_chain=title),
        )]

    chunks = []
    for chunk in raw_chunks:
        # 标题链：h1 > h2 > h3
        chain_parts = [str(chunk.metadata[k]) for _, k in _HEADERS if chunk.metadata.get(k)]
        header_chain = " > ".join(chain_parts)
        # 当前标题：取最深层级
        title = ""
        for _, k in reversed(_HEADERS):
            if chunk.metadata.get(k):
                title = str(chunk.metadata[k])
                break
        # 清理中间 key，写入最终 metadata
        for _, k in _HEADERS:
            chunk.metadata.pop(k, None)
        chunk.metadata.update(_base_meta(parsed_doc, title=title, header_chain=header_chain))
        chunks.append(chunk)

    logger.debug(f"标题切分: {len(chunks)} 个章节片段")
    return chunks


def _base_meta(parsed_doc: ParsedDocument, title: str = "", header_chain: str = "") -> dict:
    """从 ParsedDocument 构建片段公共元数据。"""
    return {
        "source_file": parsed_doc.metadata.get("parent_id", ""),
        "source_name": parsed_doc.metadata.get("filename", ""),
        "category": parsed_doc.metadata.get("category", ""),
        "title": title,
        "header_chain": header_chain,
    }


# ===================== 语义二次切分 =====================

def _resplit_long(chunks: List[Document], max_size: int) -> List[Document]:
    """超长片段按段落/句子边界再切，子片段继承原 metadata。"""
    result = []
    for chunk in chunks:
        if len(chunk.page_content) <= max_size:
            result.append(chunk)
            continue
        for sub in _greedy_split(chunk.page_content, max_size):
            result.append(Document(page_content=sub, metadata=dict(chunk.metadata)))
        logger.debug(
            f"二次切分: '{chunk.metadata.get('title', '')}' "
            f"({len(chunk.page_content)}字 → {len(result)}片段)"
        )
    return result


def _greedy_split(text: str, max_size: int) -> List[str]:
    """按段落→句子→强制截断三级策略贪心装箱。"""
    # 第 1 轮：段落边界
    fragments = _pack(text.split("\n\n"), max_size, sep="\n\n")
    # 第 2 轮：仍超长的片段按句子边界再切
    final = []
    for frag in fragments:
        if len(frag) <= max_size:
            final.append(frag)
        else:
            sentences = [s for s in _SENTENCE_BOUNDARY.split(frag) if s.strip()]
            final.extend(_pack(sentences, max_size, sep="") or [frag])
    return final or [text]


def _pack(pieces: List[str], max_size: int, sep: str) -> List[str]:
    """将 pieces 贪心拼入片段，每个片段不超过 max_size；超长单件强制截断。"""
    fragments: List[str] = []
    current = ""
    for piece in pieces:
        candidate = current + sep + piece if current else piece
        if len(candidate) <= max_size:
            current = candidate
        else:
            if current:
                fragments.append(current)
            if len(piece) > max_size:
                for j in range(0, len(piece), max_size):
                    fragments.append(piece[j:j + max_size])
                current = ""
            else:
                current = piece
    if current:
        fragments.append(current)
    return fragments


# ===================== 图片提取 =====================

def _extract_image_docs(parsed_doc: ParsedDocument) -> List[Document]:
    """从 ParsedDocument.images 生成独立的图片 Document。"""
    docs = []
    for img in parsed_doc.images:
        alt = img.get("alt", "")
        docs.append(Document(
            page_content=alt,
            metadata={
                **_base_meta(parsed_doc, title=alt or "图片"),
                "image_path": img.get("path", ""),
            },
        ))
    logger.debug(f"图片分离: {len(docs)} 张")
    return docs


# ===================== 合并过小片段 =====================

def _merge_small(chunks: List[Document], min_size: int) -> List[Document]:
    """过小片段合并到相邻片段（优先向后）。"""
    if not chunks or min_size <= 0:
        return chunks
    merged = list(chunks)
    i = 0
    while i < len(merged):
        if len(merged[i].page_content) < min_size:
            if i + 1 < len(merged):
                # 向后合并
                a, b = merged[i], merged[i + 1]
                merged[i] = Document(
                    page_content=a.page_content + "\n\n" + b.page_content,
                    metadata=dict(a.metadata),
                )
                merged.pop(i + 1)
                continue
            elif i - 1 >= 0:
                # 向前合并
                a, b = merged[i - 1], merged[i]
                merged[i - 1] = Document(
                    page_content=a.page_content + "\n\n" + b.page_content,
                    metadata=dict(a.metadata),
                )
                merged.pop(i)
                break
            else:
                i += 1
        else:
            i += 1
    if len(merged) < len(chunks):
        logger.debug(f"小片段合并: {len(chunks)} → {len(merged)}")
    return merged
