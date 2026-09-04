"""
Embedding 向量化模块 — 使用 HuggingFace bge-small-zh-v1.5 本地模型。

图片通过 alt/OCR 文本间接实现图文检索，非多模态向量。
"""

import asyncio
from typing import Optional

from langchain_core.embeddings import Embeddings
from graph_rag.config import get_settings
from util_tools.logger import get_logger

logger = get_logger(__name__)


def create_embedder(
    model_name: str | None = None,
    device: str | None = None,
) -> Embeddings:
    """创建 HuggingFace Embedding 实例。

    配置与 vector_db/collections.py 中 PGVectorManager._set_up_embeddings() 一致，
    保证入库向量和检索向量在同一个向量空间中。

    Args:
        model_name: HuggingFace 模型名，默认从 config 读取
        device: 推理设备，默认从 config 读取

    Returns:
        实现 langchain_core.embeddings.Embeddings ABC 的 HuggingFaceEmbeddings 实例
    """
    from langchain_huggingface import HuggingFaceEmbeddings

    s = get_settings()
    _model = model_name or s.embedding_model_name
    _device = device or s.embedding_device
    logger.info(f"创建 HuggingFace Embedding: model={_model}, device={_device}")
    return HuggingFaceEmbeddings(
        model_name=_model,
        model_kwargs={"device": _device},
        encode_kwargs={"normalize_embeddings": True},
    )


# ===================== 便捷函数 =====================

async def aembed_documents(texts: list[str], embedder: Optional[Embeddings] = None) -> list[list[float]]:
    """异步批量文本向量化。

    将 HuggingFace 推理（CPU/GPU 密集型）丢给线程池执行，
    不阻塞事件循环，适合与异步入库管线配合使用。

    Args:
        texts: 待向量化的文本列表
        embedder: Embedding 实例，默认调用 create_embedder() 创建

    Returns:
        向量列表，每个向量长度由模型决定（bge-small-zh-v1.5 为 512）
    """
    if embedder is None:
        embedder = create_embedder()
    return await asyncio.to_thread(embedder.embed_documents, texts)


async def aembed_query(text: str, embedder: Optional[Embeddings] = None) -> list[float]:
    """异步单条文本向量化，用于查询向量。

    Args:
        text: 查询文本
        embedder: Embedding 实例

    Returns:
        单个向量
    """
    if embedder is None:
        embedder = create_embedder()
    results = await asyncio.to_thread(embedder.embed_documents, [text])
    return results[0]
