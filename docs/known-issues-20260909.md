# 已知问题记录（2026-09-09）

> 背景：sparsevec 检索已启用、内存 BM25 检索路径已下线（docstring 已同步）。
> 以下两处为**代码层残留**，尚未处理，先记录在案。

## 1. `orchestrator.py` 仍调用已删除的 `rebuild_bm25_index()`

- **位置**：`src/graph_rag/orchestrator.py:78`（`_BM25Index.get()` 内）
- **问题**：`HybridRetrievalModule` 已无 `rebuild_bm25_index()` 方法（BM25 整套机器已随 sparsevec 检索下线），
  首次调用 `_BM25Index.get()` 触发单例构建时会抛 `AttributeError`。
- **影响**：`GraphRAGOrchestrator` 初始化直接断链，属于运行时必现错误。
- **建议**：删除该调用；单例构建时不再需要重建任何内存索引
  （sparsevec 检索走 PG SQL，索引由入库侧 `build_sparse_vector_indexes()` 维护）。

## 2. `db_retriever.initialize()` 保留 BM25 构建死代码

- **位置**：`src/graph_rag/vector_db/db_retriever.py` 的 `HybridRetrievalModule.initialize()` 及 `_build_parent_map()`
- **问题**：`initialize()` 内仍构建 `BM25Okapi` 索引并写入 `self.bm25_corpus_docs`，
  `_build_parent_map()` 也依赖该字段；但 `bm25_search()` 已删除、`initialize()` 无调用方，
  整段为死代码。
- **影响**：仅维护噪音 + 误导（docstring 仍暗示 BM25 生命周期），无运行时影响。
- **建议**：删除 `initialize()`、`_build_parent_map()`、`_CHINESE_STOPWORDS`、`_tokenize_chinese()`
  等 BM25 残留（若父文档映射仍需保留，应移到 `context_fusion` 职责下重建）。
