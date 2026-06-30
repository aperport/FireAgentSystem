"""
向量检索引擎 — 基于 PostgreSQL + pgvector + Python rank_bm25 提供三种检索策略。

检索策略：
    1. dense（稠密检索）：PG pgvector 余弦相似度，适合语义模糊查询
    2. sparse（稀疏检索）：Python jieba + rank_bm25，适合条款号/设备型号等精确关键词查询
    3. hybrid（混合检索）：dense + sparse 在 Python 层 RRF 融合，兼顾语义和关键词，推荐默认使用

检索参数：
    - query：查询文本
    - search_type：dense / sparse / hybrid
    - top_k：返回条数
    - category：按分类过滤（regulation / standard / manual / faq）
    - score_threshold：最低相似度阈值

BM25 索引生命周期：
    - 初始化时从 PG 加载全部 text 字段 → jieba 分词 → 构建 BM25Okapi 索引
    - 数据入库后需调用 rebuild_bm25_index() 重建索引

"""
import hashlib
import jieba
from langchain_core.documents import Document
from langchain_core.runnables import RunnableConfig
from rank_bm25 import BM25Okapi
from graph_rag.vector_db.collections import LOAD_ALL_TEXT_SQL, DENSE_SEARCH_SQL
from util_tools.logger import get_logger


logger = get_logger(__name__)


# 中文停用词表：助词 / 连词 / 疑问词 / 人称 / 语气词 / 动词修饰（网上有类似的包，但需要考虑实际项目）
_CHINESE_STOPWORDS = set("""
的 了 和 是 在 我 有 就 不 也 都 还 这 那 一 个 与 及 等 上 下 中 为 以 于 从 把 被 让 使 又 而 但 或
什么 怎么 如何 哪些 哪个 哪里 谁 多少 几 你 他 她 它 我们 他们 她们 它们
请问 请 想 要 需要 能 可以 应该 会 啊 呢 吧 嘛 吗 哦 呀 哈
之 其 此 该 即 各 每 些 种 类 时 后 前 里 外 内 间 已经 正在 一些 一下
""".split())


class HybridRetrievalModule:
    """
    混合检索模块

    2. BM25关键词检索（jieba分词+停用词过滤）
    3. 相似度检索（余弦相似度）
    4. RRF 融合，融合三路检索结果
    """
    def __init__(self, PGV_module,llm_client,config:RunnableConfig|None=None):
        self.config = config
        self.PGV_module = PGV_module
        self.llm_client = llm_client

        # BM25 索引 + 原始文档
        self.bm25: BM25Okapi| None = None
        self.bm25_corpus_docs: list[Document] = []


    def rebuild_bm25_index(self):
        """从 PG 重新加载全部文本，重建 BM25 索引"""
        cur = self.PGV_module.get_cursor()
        cur.execute(LOAD_ALL_TEXT_SQL)
        rows = cur.fetchall()
        chunks = []
        for row in rows:
            chunks.append(Document(page_content=row["text"], metadata={"id": row["id"], "category": row["category"], "source_hash": row["source_hash"],"source_name": row["source_name"],"title": row["title"]}))
        
        self.initialize(chunks)

    def initialize(self,chunks:list[Document]):
        """初始化检索系统"""

        # 初始化 BM25（jieba 分词 + 中文停用词过滤）
        if chunks:
            self.bm25_corpus_docs = list(chunks)
            # 将文档通过分词分成单词，然后过滤掉中文停用词，再构建 BM25 索引
            tokenized_corpus = [self._tokenize_chinese(doc.page_content) for doc in chunks]
            self.bm25 = BM25Okapi(tokenized_corpus)
            avg_token = sum(len(t) for t in tokenized_corpus) / max(len(tokenized_corpus),1)
            logger.info(f"BM25 索引构建完成，平均单词数：{avg_token},文档数量：{len(chunks)}")

        # 初始化 父文档映射表
        self.parent_map = self._build_parent_map()
        logger.info("父文档映射表构建完成，文档数量：{}".format(len(self.parent_map)))

    @staticmethod
    def _tokenize_chinese(text:str) ->list[str]:
        """中文分词（过滤停用词）""" 
        if not text:
            return []
        return [token for token in jieba.lcut(text) if token not in _CHINESE_STOPWORDS and token.strip()]
    


    def bm25_search(self,query:str,top_K:int = 5)->list[Document]:
        """
        BM25 关键词检索,在使用jieba分词后，查BM250索引，按分数降序返回k调数据，分数计入metadata,供以后调试或者分数融合使用
        args:
            query: 查询关键词
            top_K: 返回前k个
        return:
            list[Document]: 返回检索结果
        """
        if self.bm25 is None:
            logger.warning("BM25 索引尚未初始化，无法进行检索")
            return []
        # 1. BM25 关键词检索
        tokenized_query = self._tokenize_chinese(query)
        if not tokenized_query:
            logger.warning("BM分词查询结果为空，无法进行检索，跳过本次查询，%s",query)
            return []
        # 按分数降序去top_k
        scores = self.bm25.get_scores(tokenized_query)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_K]
        docs:list[Document] = []
        for index in top_indices:
            score = float(scores[index])
            if score < 0.1:
                continue
            src = self.bm25_corpus_docs[index]
            new_metadata = dict(src.metadata)
            new_metadata["score"] = score
            new_metadata["search_type"] = "bm25"

            doc = Document(page_content=src.page_content, metadata=new_metadata)
            docs.append(doc)
            logger.info(f"BM25 关键词检索结果：{doc.page_content}，分数：{score}")
        return docs
    

    def dense_search(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
        score_threshold: float = 0.1,
        table_name: str = "fire_doc_collection",
    ) -> list[Document]:
        """稠密向量检索（PG pgvector 余弦相似度）

        通过 Embedding 将查询文本向量化，然后在 PostgreSQL 中使用
        pgvector 的余弦距离操作符 <=> 进行相似度检索。

        Args:
            query: 查询文本
            top_k: 返回前 k 个结果
            category: 按分类过滤（regulation / standard / manual / faq），None 表示不过滤
            score_threshold: 最低相似度阈值，低于此值的结果将被过滤
            table_name: 查询的表名，默认 fire_doc_collection

        Returns:
            list[Document]: 检索结果列表，metadata 中包含 score 和 search_type
        """
        if self.PGV_module is None:
            logger.warning("PGV_module 未初始化，无法进行稠密检索")
            return []

        try:
            # 1. 查询文本向量化
            query_vector = self.PGV_module.embeddings.embed_query(query)

            # 2. 构建分类过滤条件
            category_filter = ""
            if category:
                category_filter = "AND category = %s"

            # 3. 组装 SQL
            sql = DENSE_SEARCH_SQL.format(
                table_name=table_name,
                category_filter=category_filter,
            )

            # 4. 执行查询（pgvector 余弦距离：向量参数传两次，一次算分数，一次排序）
            cur = self.PGV_module.get_cursor()
            if category:
                cur.execute(sql, (query_vector, category, query_vector, top_k))
            else:
                cur.execute(sql, (query_vector, query_vector, top_k))

            rows = cur.fetchall()

            # 5. 转换为 Document 列表
            docs: list[Document] = []
            for row in rows:
                score = float(row["score"])
                if score < score_threshold:
                    continue
                doc = Document(
                    page_content=row["text"],
                    metadata={
                        "id": row["id"],
                        "category": row["category"],
                        "source_hash": row["source_hash"],
                        "title": row["title"],
                        "source_name": row["source_name"],
                        "score": score,
                        "search_type": "dense",
                    },
                )
                docs.append(doc)
                logger.info(f"Dense 检索结果：{doc.page_content[:80]}...，分数：{score:.4f}")

            return docs

        except Exception as e:
            logger.error(f"稠密向量检索失败：{e}")
            return []
    
    @staticmethod
    def _rrf_merge(
        ranked_list: list[tuple[str, list[Document]]],  top_k: int ,k: int = 60
    )-> list[Document]:
        """RRF 融合，去重之后计算等分排名，返回前k个
                Reciprocal Rank Fusion: score(d) = Σ_i 1 / (k + best_rank_i(d))
        args:
            ranked_list: list[tuple[str, list[Document]]], 检索结果
            top_k: 返回前k个
            k: 平滑常熟，默认取60.
        去重 key：PG id 优先，page_content[:200] hash 兜底。
        同一 id 在同一 source 内多次命中只取最佳 rank 算分一次。
        """
        # doc_id -> source_name -> 该 source 内最小 rank（用于算分）
        best_rank_per_source: dict[str, dict[str, int]] = {}
        # doc_id -> source_name -> 该 source 内命中 chunk 次数
        chunk_hits_per_source: dict[str, dict[str, int]] = {}
        # doc_id -> (global_best_rank, source_priority, doc) — 选 canonical doc
        best_doc_info: dict[str, tuple[int, int, Document]] = {}

        for source_priority, (source_name, ranked_docs) in enumerate(ranked_list):
            for rank, doc in enumerate(ranked_docs, start=1):
                # 去重 key：PG id 优先，page_content hash 兜底
                pg_id = doc.metadata.get("id")
                doc_id = (
                    str(pg_id) if pg_id is not None
                    else f"hash::{hashlib.md5(doc.page_content[:200].encode('utf-8')).hexdigest()}"
                )

                if doc_id not in best_rank_per_source:
                    best_rank_per_source[doc_id] = {}
                    chunk_hits_per_source[doc_id] = {}

                curr_best = best_rank_per_source[doc_id].get(source_name)
                if curr_best is None or rank < curr_best:
                    best_rank_per_source[doc_id][source_name] = rank

                chunk_hits_per_source[doc_id][source_name] = (
                    chunk_hits_per_source[doc_id].get(source_name, 0) + 1
                )

                new_key = (rank, source_priority)
                if (
                    doc_id not in best_doc_info
                    or new_key < (best_doc_info[doc_id][0], best_doc_info[doc_id][1])
                ):
                    best_doc_info[doc_id] = (rank, source_priority, doc)

        # 每个 source 只用 best rank 算一次贡献
        rrf_scores: dict[str, float] = {
            doc_id: sum(1.0 / (k + r) for r in source_ranks.values())
            for doc_id, source_ranks in best_rank_per_source.items()
        }

        sorted_ids = sorted(rrf_scores.keys(), key=lambda d: rrf_scores[d], reverse=True)

        merged: list[Document] = []
        for doc_id in sorted_ids[:top_k]:
            _, _, source_doc = best_doc_info[doc_id]
            new_metadata = dict(source_doc.metadata)
            new_metadata["rrf_score"] = rrf_scores[doc_id]
            new_metadata["rrf_sources"] = list(best_rank_per_source[doc_id].keys())
            new_metadata["rrf_ranks"] = dict(best_rank_per_source[doc_id])
            new_metadata["rrf_chunk_hits"] = dict(chunk_hits_per_source[doc_id])
            new_metadata["final_score"] = rrf_scores[doc_id]
            merged.append(Document(
                page_content=source_doc.page_content,
                metadata=new_metadata,
            ))

        return merged

    
    def _build_parent_map(self) -> dict[str, list[Document]]:
        """构建父文档映射表

        将 bm25_corpus_docs 中的子文档按 source_hash 分组，
        形成 source_hash -> [Document, ...] 的映射关系。
        用于检索命中子文档后，回填同一 source_hash 下的完整父文档内容，
        提供更丰富的上下文信息。

        Returns:
            dict[str, list[Document]]: source_hash -> 同源子文档列表
        """
        parent_map: dict[str, list[Document]] = {}
        for doc in self.bm25_corpus_docs:
            source_hash = doc.metadata.get("source_hash", "")
            if not source_hash:
                continue
            if source_hash not in parent_map:
                parent_map[source_hash] = []
            parent_map[source_hash].append(doc)
        return parent_map

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        category: str | None = None,
        score_threshold: float = 0.1,
        rrf_k: int = 60,
    ) -> list[Document]:
        """混合检索（dense + sparse RRF 融合）

        同时执行稠密向量检索和 BM25 关键词检索，然后使用
        Reciprocal Rank Fusion (RRF) 融合两路结果，兼顾语义和关键词匹配。

        Args:
            query: 查询文本
            top_k: 最终返回前 k 个结果
            category: 按分类过滤
            score_threshold: 最低相似度阈值
            rrf_k: RRF 平滑常数，默认 60

        Returns:
            list[Document]: RRF 融合后的检索结果
        """
        # 1. 并行执行两路检索（各取 top_k * 2 扩大候选集）
        expand_k = top_k * 2
        dense_docs = self.dense_search(query, top_k=expand_k, category=category, score_threshold=score_threshold)
        sparse_docs = self.bm25_search(query, top_K=expand_k)

        # 2. RRF 融合
        ranked_list: list[tuple[str, list[Document]]] = [
            ("dense", dense_docs),
            ("bm25", sparse_docs),
        ]
        merged = self._rrf_merge(ranked_list, top_k=top_k, k=rrf_k)

        # 标记检索类型
        for doc in merged:
            doc.metadata["search_type"] = "hybrid"

        logger.info(
            f"Hybrid 检索完成：dense={len(dense_docs)}, bm25={len(sparse_docs)}, "
            f"融合后={len(merged)}"
        )
        return merged
    
    




 
        






        


        

        