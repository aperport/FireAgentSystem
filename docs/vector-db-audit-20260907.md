# vector_db 三模块审计（2026-09-07）

> 范围：`src/graph_rag/vector_db/` 下的 `collections.py`、`db_operator.py`、`db_retriever.py`。
> 背景：三个模块编写时间较早、追加式生长（三路检索逐个往上摞），本文记录职责现状、问题清单与重构优先级，供后续整理参考。

## 一、职责现状

### collections.py — PGVectorManager（3 个职责，中度混杂）

| 职责 | 成员 |
|---|---|
| 连接管理 | `_connect` / `get_cursor` / `close` / `get_pg_instance` 单例 |
| DDL 运维 | `init_tables` / `build_vector_indexes` + 文件级 DDL / 索引常量 |
| Embedding 模型 | `_set_up_embeddings` → `self.embeddings`（与 PG 无关的计算资源） |

文件同时承载：表 DDL、查询 SQL 模板、连接管理器、单例工厂，双向服务 db_operator（写入）与 db_retriever（检索），天然容易变成共享垃圾场。文件头 docstring 已自知此问题并留有拆分计划（第 36-39 行）。

### db_operator.py — DBOperator（单一职责，基本健康）

- 仅负责写入：`insert_chunks` / `insert_picture` 已合并出公共方法 `_insert_documents`，重复逻辑少。
- 唯一问题是穿透访问 `self.pg.embeddings.embed_documents(...)`（db_operator.py:80），这是 collections 混杂职责的下游症状，不是本模块自己的病。

### db_retriever.py — HybridRetrievalModule（5 个职责，上帝类）

1. dense 检索：穿透 `PGV_module.embeddings` 向量化 + 拿 cursor 查 PG（db_retriever.py:193）
2. BM25 索引生命周期：jieba 分词、停用词过滤、启动/入库后从 PG 全量拉 text 重建索引
3. BM25 检索：`bm25_search`
4. RRF 融合纯算法：`_rrf_merge`（staticmethod，本可为模块级函数）
5. 父文档映射：`_build_parent_map`（db_retriever.py:310）——本属 `context_fusion` 的职责，后者只是消费者（context_fusion.py:47）

## 二、问题清单

| # | 问题 | 位置 | 影响 |
|---|---|---|---|
| 1 | 构造函数强制加载 HuggingFace 模型，只要 DB 连接也背上模型开销 | collections.py `__init__` | 初始化重、阻塞；测试需连带 mock embedding |
| 2 | `HuggingFaceEmbeddings` 全仓 4 处独立实例化（collections / ingestion/embedding / graph_vector_traverser:181 / evaluator:130） | 全仓 | 两处配置只靠注释「保持一致」维系，漂移则入库/检索向量空间不一致（静默的严重 bug） |
| 3 | 调用方穿透访问 `pg.embeddings` | db_operator.py:80、db_retriever.py:193 | 依赖链不自然（embed_query 不需要数据库） |
| 4 | 死代码 `GET_BY_SOURCE_FILE_SQL` 全仓无调用方 | collections.py:119 | 维护噪音 |
| 5 | 死参数 `llm_client` / `config: RunnableConfig` 注入后零使用 | db_retriever.py:74 | 预留未用，误导维护者 |
| 6 | `parent_map` 构建职责错位 | db_retriever.py:310 | 检索模块承担了上下文组装的数据准备 |
| 7 | BM25 全量进内存 vs pgvector 原生 sparse vector 路线未定 | collections.py:128 注释 | 决定 BM25 相关重构是否值得做 |

## 三、重构建议（按优先级）

**P0 — 立即可做（低风险、高收益）**

- Embedding 从 `PGVectorManager` 剥离：删除 `model_name` 参数、`_set_up_embeddings`、`self.embeddings`。
- Embedding 收敛到已有的 `ingestion/embedding.py`：加全局懒加载单例，db_operator / db_retriever 改为注入使用，删除 `pg.embeddings` 穿透访问。
- 删除死代码与死参数：`GET_BY_SOURCE_FILE_SQL`、`llm_client`、`config`。
- `get_pg_instance()` 签名去掉 `model_name`，外部调用方（orchestrator.py）无需改动。

**P1 — 无悔重构（不依赖存储决策）**

- `_rrf_merge` 从方法挪为模块级纯函数（已是 staticmethod，无状态）。
- `parent_map` 构建移交 `context_fusion`，db_retriever 只保留三路检索与融合。

**P2 — 待决策后再动**

- BM25 是否切换 pgvector 原生稀疏向量：若切换，db_retriever 中分词 / 停用词 / 索引重建整套机器会被删除。**先拆 BM25 可能白拆**，建议等存储方案定稿后一并处理。

## 四、不做的事（避免过度设计）

- 不单独拆 `VectorSchemaManager`：`init_tables` / `build_vector_indexes` 依赖连接且调用频率低，留在连接管理器内即可。
- 不为「未来可能的异步化」预先引入抽象：`db_retriever.py` 的同步阻塞问题（文件头已知问题 1）先用 `asyncio.to_thread` 包一层即可解决，等真实需求出现再考虑接口级改动。
