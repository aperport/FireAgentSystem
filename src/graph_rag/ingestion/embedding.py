"""
Embedding 向量化模块 — 使用 FlagEmbedding BGE-M3 本地模型。

BGE-M3 一次 encode 同时产出：
    - dense_vecs      稠密语义向量，1024 维（写入 PG vector(1024)）
    - lexical_weights 稀疏向量（token_id -> 权重），写入 PG sparsevec

图片通过 alt/OCR 文本间接实现图文检索，非多模态向量。
"""

import asyncio
from functools import lru_cache
from typing import Any

from FlagEmbedding import BGEM3FlagModel
from langchain_core.embeddings import Embeddings

from graph_rag.config import get_settings
from util_tools.logger import get_logger

logger = get_logger(__name__)


class BGEM3EmbeddingsAdapter(Embeddings):
    """将 BGEM3FlagModel 适配为 langchain Embeddings 接口（仅 dense）。

    供 ragas 等要求 langchain Embeddings 的组件使用；
    项目内部入库/检索请直接用 get_embedder() / encode_* 函数。
    """

    def __init__(self, embedder: BGEM3FlagModel | None = None):
        self._embedder = embedder or get_embedder()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        outputs = self._embedder.encode(
            texts,
            return_dense=True,
            return_sparse=False,
            return_colbert_vecs=False,
        )
        return [vec.tolist() for vec in outputs["dense_vecs"]]

    def embed_query(self, text: str) -> list[float]:
        return encode_query_dense(text, self._embedder)


def create_embedder(
    model_name: str | None = None,
    device: str | None = None,
) -> BGEM3FlagModel:
    """创建 BGE-M3 Embedding 实例。

    配置统一从 config 读取。全项目应通过 get_embedder() 单例获取实例，
    保证入库向量和检索向量在同一个向量空间中。

    BGEM3FlagModel 构造签名（1.2.x）：
        BGEM3FlagModel(model_name_or_path, use_fp16=..., devices=...)

    Args:
        model_name: HuggingFace 模型名，默认从 config 读取
        device: 推理设备（如 "cpu" / "cuda"），默认从 config 读取

    Returns:
        BGEM3FlagModel 实例
    """
    s = get_settings()
    _model = model_name or s.embedding_model_name
    _device = device or s.embedding_device
    logger.info(f"创建 BGE-M3 Embedding: model={_model}, device={_device}")
    return BGEM3FlagModel(
        model_name_or_path=_model,
        use_fp16=False,  # CPU 下 fp16 无收益且部分算子不支持
        devices=[_device],
    )


def encode_query_dense(query: str, embedder: BGEM3FlagModel | None = None) -> list[float]:
    """查询文本 → 稠密向量（用于 pgvector dense 检索）。

    BGE-M3 的 query/passage 均走同一 encode，无需区分 instruction 前缀。
    """
    if embedder is None:
        embedder = get_embedder()
    outputs = embedder.encode(
        [query],
        return_dense=True,
        return_sparse=False,
        return_colbert_vecs=False,
    )
    return outputs["dense_vecs"][0].tolist()


def encode_query_sparse(query: str, embedder: BGEM3FlagModel | None = None) -> dict[int, float]:
    """查询文本 → 稀疏向量 {token_id: 权重}（用于 pgvector sparsevec 检索）。"""
    if embedder is None:
        embedder = get_embedder()
    outputs = embedder.encode(
        [query],
        return_dense=False,
        return_sparse=True,
        return_colbert_vecs=False,
    )
    return {int(k): float(v) for k, v in outputs["lexical_weights"][0].items()}


def encode_hybrid(
    texts: list[str],
    embedder: BGEM3FlagModel | None = None,
) -> list[dict[str, Any]]:
    """批量文本 → [{dense: list[float], sparse: dict[int, float]}, ...]

    一次 encode 同时取 dense + sparse，供入库与图向量精排共用。
    """
    if embedder is None:
        embedder = get_embedder()
    outputs = embedder.encode(
        texts,
        return_dense=True,
        return_sparse=True,
        return_colbert_vecs=False,
    )
    results = []
    for dense, sparse in zip(outputs["dense_vecs"], outputs["lexical_weights"]):
        results.append(
            {
                "dense": dense.tolist(),
                "sparse": {int(k): float(v) for k, v in sparse.items()},
            }
        )
    return results


# ===================== 便捷函数 =====================


async def aembed_documents(texts: list[str], embedder: BGEM3FlagModel | None = None) -> list[list[float]]:
    """异步批量文本向量化（线程池执行，不阻塞事件循环）。"""
    if embedder is None:
        embedder = get_embedder()
    return await asyncio.to_thread(
        lambda: [item["dense"] for item in encode_hybrid(texts, embedder)]
    )


async def aembed_query(text: str, embedder: BGEM3FlagModel | None = None) -> list[float]:
    """异步单条文本向量化，用于查询向量。"""
    if embedder is None:
        embedder = get_embedder()
    return await asyncio.to_thread(encode_query_dense, text, embedder)


# ===================== 全局单例 =====================


@lru_cache(maxsize=1)
def get_embedder() -> BGEM3FlagModel:
    """获取全局 Embedding 单例（懒加载）。

    入库（db_operator）与检索（db_retriever / graph_vector_traverser）
    共用同一模型实例，避免多处各自实例化导致配置漂移、
    入库/检索向量空间不一致。
    测试如需重置，调用 get_embedder.cache_clear()。
    """
    return create_embedder()
