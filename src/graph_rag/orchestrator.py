"""
GraphRAG 查询编排器 — 整个 GraphRAG Pipeline 的核心入口。

负责协调以下步骤：
    1. 实体抽取：从用户自然语言问题中提取关键实体（LLM + NER 并行）
    2. 并行检索：向量检索(PG pgvector) + 图遍历(Neo4j) 同时进行
    3. 去重融合：合并向量片段与图路径，按相关性排序，截断至Token预算
    4. 结果持久化：将查询及各阶段结果存入 JSON，用于后续评估和训练

对外接口：
    GraphRAGOrchestrator(query).rag_search() -> list[Document]

由 MCP Tool (knowledge_tools.py 中的 graph_rag_search) 调用。

"""
import asyncio
import sys, os
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from langchain_core.language_models import BaseChatModel
from graph_rag.config import get_settings
from graph_rag.context_fusion import ContextFusionModule
from graph_rag.entity_extractor import DocumentGraphExtractionPipeline, ExtractResult

from graph_rag.graph_traverser import GraphTraverser
from graph_rag.json_save import append_json_item
from graph_rag.vector_db.collections import get_pg_instance
from graph_rag.vector_db.db_retriever import HybridRetrievalModule
from graph_rag.vector_retriever import VectorRetriever
from util_tools.logger import get_logger

logger = get_logger(__name__)


# ===================== 全局单例：BM25 索引 =====================

_LLM: BaseChatModel | None = None


def _get_llm() -> BaseChatModel:
    """获取注入的 LLM 实例，未注入则报错。"""
    if _LLM is None:
        raise RuntimeError("未注入 LLM，请先调用 set_llm() 或在构造时传入 llm 参数")
    return _LLM


def set_llm(llm: BaseChatModel) -> None:
    """设置全局 LLM 实例（由 Agent 层在启动时调用）。"""
    global _LLM
    _LLM = llm


class _BM25Index:
    """BM25 索引全局单例（进程级缓存）。

    首次访问时从 PG 加载全表文本构建 BM25Okapi 索引，后续直接复用。
    数据入库后调用 rebuild() 重建。
    """
    _instance: HybridRetrievalModule | None = None
    _lock = threading.Lock()

    @classmethod
    def get(cls) -> HybridRetrievalModule:
        """获取 BM25 索引实例（懒加载）。"""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is not None:
                    return cls._instance
                s = get_settings()
                pg = get_pg_instance(
                    host=s.pg_host,
                    user=s.pg_user,
                    password=s.pg_password,
                    dbname=s.pg_dbname,
                    port=s.pg_port,
                )
                cls._instance = HybridRetrievalModule(
                    PGV_module=pg,
                    llm_client=_get_llm(),
                )
                cls._instance.rebuild_bm25_index()
                logger.info("BM25 索引全局单例构建完成")
        return cls._instance

    @classmethod
    def rebuild(cls) -> HybridRetrievalModule:
        """数据入库后调用，重建 BM25 索引。"""
        logger.info("BM25 索引重建触发")
        with cls._lock:
            cls._instance = None
        return cls.get()


# ===================== 全局单例：Neo4j 驱动 =====================




class GraphRAGOrchestrator:
    def __init__(self, graph_traverser: GraphTraverser, doc_extraction:DocumentGraphExtractionPipeline, context_fusion: ContextFusionModule, vector_retriever: VectorRetriever):
        self.retrieval_module = _BM25Index.get()
        self.graph_traverser = graph_traverser
        self.doc_extraction = doc_extraction
        self.context_fusion = context_fusion
        self.vector_retriever = vector_retriever

    async def rag_search(self, query: str, top_k=5):
        # 1. 对问题进行实体抽取
        entity_result = await self.doc_extraction.extract(query)
        # 2. 对实体进行向量检索与图遍历
        # 2.1 向量检索
        vector_task = self.vector_retriever.search(query=query,top_k=top_k)

        # 2.2 图遍历
        async def _graph_traverser():
            if  isinstance(entity_result, ExtractResult):
                return  await self.graph_traverser.traverse(entity_result)
            else:
                logger.info("提取的类型不正确")
            return   []

        graph_task =  _graph_traverser()

        # 前面创建协程，不要加await，此处使用asyncio.gather并发执行两方法
        vector_result, graph_result = await asyncio.gather(vector_task, graph_task)
        # 3. 对检索结果进行去重融合
        result = await self.context_fusion.fuse(vector_docs=vector_result, graph_records=graph_result) # type: ignore

        # 4. 将答案存入json，model_dump是pydantic的方法，会将这个类的属性转换成字典
        Data = {
            "query": query,
            "entity_result": entity_result.model_dump() if hasattr(entity_result, "model_dump") else str(entity_result),
            "vector_result": [doc.model_dump() if hasattr(doc, "model_dump") else {"page_content": doc.page_content, "metadata": doc.metadata} for doc in vector_result],
            "graph_result": graph_result,
            "result": [doc.model_dump() if hasattr(doc, "model_dump") else {"page_content": doc.page_content, "metadata": doc.metadata} for doc in result]
        }
        await append_json_item(dir_name="./data/", item=Data, file_name="T")

        return result


