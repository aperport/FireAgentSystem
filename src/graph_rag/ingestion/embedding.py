"""
Embedding 向量化模块 — 将文本转化为向量，供 PG pgvector 或下游入库使用。

✅ 已实现。使用 HuggingFace 本地 Embedding（BAAI/bge-small-zh-v1.5, 512维），
    与 vector_db/collections.py 中的 PGVectorManager 使用同一模型，
    保证入库向量和检索向量的空间一致。

⚠️ 图片向量化说明：
    bge-small-zh-v1.5 是纯文本模型，不支持图片向量化。
    当前图片文档（fire_image_collection）的入库策略：
        - 图片的 text 字段用 alt 文本 / OCR 文本填充
        - 用 bge-small-zh-v1.5 对该文本做向量化（间接实现图文检索）
        - 若需真正的多模态向量化（图片像素级 Embedding），
          需引入 DashScope multimodal-embedding-v1 或 CLIP 等多模态模型

使用方式：
    from graph_rag.ingestion.embedding import create_embedder
    embedder = create_embedder()
    vectors = embedder.embed_documents(["文本1", "文本2"])

向量化结果写入 PG 的方式：
    方案 A（当前）：由 DBOperator 内部调用 self.pg.embeddings.embed_documents() 自动向量化
    方案 B（推荐）：由调用方先用本模块生成向量，再传给 DBOperator 写入
        → 需后续重构 DBOperator，使其支持接收预计算向量

环境变量：
    EMBEDDING_MODEL_NAME  HuggingFace 模型名（默认 BAAI/bge-small-zh-v1.5）
    EMBEDDING_DEVICE      推理设备 cuda / cpu（默认 cuda）
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
