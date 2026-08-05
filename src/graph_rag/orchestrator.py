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
import sys, os
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agent.llm_config import DeepSeek_LLM
from graph_rag.config import get_settings
from graph_rag.context_fusion import ContextFusionModule
from graph_rag.entity_extractor import EntityExtractor
from graph_rag.graph_traverser import GraphTraverser
from graph_rag.json_save import append_json_item
from graph_rag.vector_db.collections import get_pg_instance
from graph_rag.vector_db.db_retriever import HybridRetrievalModule
from graph_rag.vector_retriever import VectorRetriever
from util_tools.logger import get_logger

logger = get_logger(__name__)


# ===================== 全局单例：BM25 索引 =====================

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
                    llm_client=DeepSeek_LLM,
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

class _Neo4jDriver:
    """Neo4j 驱动全局单例。"""
    _instance: GraphTraverser | None = None

    @classmethod
    def get(cls) -> GraphTraverser:
        if cls._instance is None:
            cls._instance = GraphTraverser(extract_result=None)
            logger.info("Neo4j GraphTraverser 全局单例构建完成")
        return cls._instance


class GraphRAGOrchestrator:
    def __init__(self, query: str):
        self.query = query
        self.retrieval_module = _BM25Index.get()

    async def rag_search(self,top_k=5):
        # 1. 对问题进行实体抽取
        entityExtractor = EntityExtractor(llm_client=DeepSeek_LLM,query=self.query)
        entity_result = await entityExtractor.main_pip()

        # 2. 对实体进行向量检索与图遍历
        # 2.1 向量检索

        vectorRetriever = VectorRetriever(retrieval_module=self.retrieval_module)
        vector_result = await vectorRetriever.search(query=self.query,top_k=top_k)

        # 2.2 图遍历
        graph_traverser = _Neo4jDriver.get()
        graph_traverser.extract_result = entity_result
        graph_result = await graph_traverser.traverse()

        # 3. 对检索结果进行去重融合
        context_fusion_module = ContextFusionModule(parent_map=self.retrieval_module.parent_map)
        result = await context_fusion_module.fuse(vector_docs=vector_result, graph_records=graph_result)

        # 4. 将答案存入json
        Data = {
            "query": self.query,
            "entity_result": entity_result.model_dump() if hasattr(entity_result, "model_dump") else str(entity_result),
            "vector_result": [doc.model_dump() if hasattr(doc, "model_dump") else {"page_content": doc.page_content, "metadata": doc.metadata} for doc in vector_result],
            "graph_result": graph_result,
            "result": [doc.model_dump() if hasattr(doc, "model_dump") else {"page_content": doc.page_content, "metadata": doc.metadata} for doc in result]
        }
        await append_json_item(dir_name="./data/", item=Data, file_name="T")

        return result


# [删除理由] 以下代码已删除：
# 1. main() + if __name__ == "__main__": 测试入口 — 生产代码不应包含模块级测试，
#    测试应放在 src/test/ 目录下，通过 pytest 运行。
# 2. GraphQuery / VectorQuery 类 — 与 GraphRAGOrchestrator.rag_search() 逻辑重复，
#    GraphRAGOrchestrator 已整合了图遍历和向量检索，这两个独立类无额外价值。
#    如需单独查询，knowledge_tools.py 已改为直接调用底层 VectorRetriever / GraphTraverser。
