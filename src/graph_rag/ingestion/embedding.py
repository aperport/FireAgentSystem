"""
Embedding 向量化模块 — 使用 HuggingFace bge-small-zh-v1.5 本地模型。

图片通过 alt/OCR 文本间接实现图文检索，非多模态向量。
"""

import os
import asyncio
from typing import Optional

from langchain_core.embeddings import Embeddings
from util_tools.logger import get_logger

logger = get_logger(__name__)

# ─── 环境变量（模块级读取，与 db_operator.py 模式一致）───
_EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh-v1.5")
_EMBEDDING_DEVICE = os.getenv("EMBEDDING_DEVICE", "cuda")


# ===================== 工厂函数 =====================

def create_embedder(
    model_name: str = _EMBEDDING_MODEL_NAME,
    device: str = _EMBEDDING_DEVICE,
) -> Embeddings:
    """创建 HuggingFace Embedding 实例。

    配置与 vector_db/collections.py 中 PGVectorManager._set_up_embeddings() 一致，
    保证入库向量和检索向量在同一个向量空间中。

    Args:
        model_name: HuggingFace 模型名，默认 BAAI/bge-small-zh-v1.5（512维）
        device: 推理设备，"cuda"（GPU）或 "cpu"

    Returns:
        实现 langchain_core.embeddings.Embeddings ABC 的 HuggingFaceEmbeddings 实例

    Example:
        # 使用默认配置（bge-small-zh-v1.5 + cuda）
        embedder = create_embedder()

        # 使用 CPU（无 GPU 环境时）
        embedder = create_embedder(device="cpu")

        # 使用其他模型
        embedder = create_embedder(model_name="BAAI/bge-large-zh-v1.5")
    """
    from langchain_huggingface import HuggingFaceEmbeddings

    logger.info(f"创建 HuggingFace Embedding: model={model_name}, device={device}")
    return HuggingFaceEmbeddings(
        model_name=model_name,
        model_kwargs={"device": device},
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
