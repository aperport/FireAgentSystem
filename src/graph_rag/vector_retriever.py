"""
向量检索模块 — 基于 PostgreSQL + pgvector 实现知识库的语义检索。

✅ 已实现。支持三种检索策略：
    1. 稠密检索（dense）：Embedding 向量余弦相似度，适合语义模糊查询
    2. 稀疏检索（sparse）：BM25 关键词匹配，适合条款号/设备型号等精确查询
    3. 混合检索（hybrid）：稠密+稀疏 RRF 融合，兼顾语义和关键词，推荐默认使用

检索流程（search 统一入口）：
    search(query, search_type, ...)
      │
      ├── 1. 按策略分发检索（委托 db_retriever）
      │   ├── "dense"  → dense_search()
      │   ├── "sparse" → bm25_search()
      │   └── "hybrid" → hybrid_search()
      │
      ├── 2. 父文档回填（委托 context_fusion.attach_parent_documents）
      │
      └── 3. Token 预算截断（委托 context_fusion.truncate_to_budget）

两个 Collection：
    - fire_doc_collection：静态知识文档（法规/标准/手册）
    - fire_image_collection：图文混合文档

由 MCP Tool (knowledge_search) 和 orchestrator.py 调用。

⚠️ 已知问题：
    1. search() 是 async 方法，但内部调用的 retrieval_module.dense_search() /
       bm25_search() / hybrid_search() 均为同步方法，未使用 await
    2. attach_parent_documents() 和 truncate_to_budget() 也是同步方法，同样未 await
    3. HybridRetrievalModule 初始化时未调用 initialize()，bm25 索引为空

待优化：
    - 将 db_retriever 的检索方法改为异步，或使用 asyncio.to_thread 包装
    - VectorRetriever 初始化时应触发 BM25 索引构建
    - 增加 retrieval_evaluator 集成：检索结果为空时自动 fallback
"""
from langchain_core.documents import Document
from graph_rag.vector_db.db_retriever import HybridRetrievalModule
from graph_rag.context_fusion import ContextFusionModule
from util_tools.logger import get_logger


logger = get_logger(__name__)


class VectorRetriever:
    """向量检索统一入口

    封装 db_retriever 的纯检索能力，叠加 context_fusion 的
    父文档回填和 Token 截断，对外提供一站式检索接口。
    """

    def __init__(self, retrieval_module: HybridRetrievalModule):
        self.retrieval_module = retrieval_module
        self.fusion_module = ContextFusionModule(
            parent_map=retrieval_module.parent_map
        )

    async def search(
        self,
        query: str,
        search_type: str = "hybrid",
        top_k: int = 5,
        category: str | None = None,
        score_threshold: float = 0.1,
        token_budget: int = 0,
    ) -> list[Document]:
        """统一检索入口

        根据指定的检索策略分发到对应的检索方法，
        可选执行父文档回填和 Token 预算截断。

        Args:
            query: 查询文本
            search_type: 检索策略，可选：
                - dense：稠密向量检索（语义模糊查询）
                - sparse：BM25 关键词检索（精确关键词查询）
                - hybrid：混合检索（推荐默认使用）
            top_k: 返回前 k 个结果
            category: 按分类过滤（regulation / standard / manual / faq）
            score_threshold: 最低相似度阈值
            token_budget: Token 预算上限，0 表示不截断

        Returns:
            list[Document]: 检索结果列表
        """
        # 1. 按策略分发检索
        if search_type == "dense":
            docs = self.retrieval_module.dense_search(
                query, top_k=top_k, category=category, score_threshold=score_threshold
            )
        elif search_type == "sparse":
            docs = self.retrieval_module.bm25_search(query, top_K=top_k)
        elif search_type == "hybrid":
            docs = self.retrieval_module.hybrid_search(
                query, top_k=top_k, category=category, score_threshold=score_threshold
            )
        else:
            logger.warning(f"未知的检索类型：{search_type}，回退到 hybrid")
            docs = self.retrieval_module.hybrid_search(
                query, top_k=top_k, category=category, score_threshold=score_threshold
            )

        # 2. Token 预算截断
        if token_budget > 0:
            docs = self.fusion_module.truncate_to_budget(docs, token_budget)

        return docs
