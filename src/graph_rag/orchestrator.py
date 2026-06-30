"""
GraphRAG 查询编排器 — 整个 GraphRAG Pipeline 的核心入口。

负责协调以下步骤：
    1. 实体抽取：从用户自然语言问题中提取关键实体
    2. 并行检索：向量检索(Milvus) + 图遍历(Neo4j) 同时进行
    3. 去重融合：合并向量片段与图路径，按相关性排序，截断至Token预算
    4. LLM生成：基于融合上下文生成结构化回答
    5. 将答案存入json，用于后续评估RAG系统质量，以及训练小模型。

对外接口：
    orchestrate(query: str, **kwargs) -> GraphRAGResult

由 MCP Tool (knowledge_tools.py 中的 graph_rag_search) 调用。
"""
from agent.llm_config import DeepSeek_LLM
from graph_rag.context_fusion import ContextFusionModule
from graph_rag.entity_extractor import EntityExtractor
from graph_rag.graph_traverser import GraphTraverser
from graph_rag.vector_db.collections import PGVectorManager
from graph_rag.vector_db.db_retriever import HybridRetrievalModule
from graph_rag.vector_retriever import VectorRetriever
from util_tools.logger import get_logger

logger = get_logger(__name__)

class GraphRAGOrchestrator:
    def __init__(self,query:str):
        self.query = query

    async def rag_search(self):
        # 1. 对问题进行实体抽取
        entityExtractor = EntityExtractor(llm_client=DeepSeek_LLM,query=self.query)
        entity_result = await entityExtractor.main_pip()

        # 2. 对实体进行向量检索与图遍历
        # 2.1 向量检索
        PGV_DB = PGVectorManager(host="localhost",user="postgres",password="",dbname="fire_rag",port=5432)
        retrieval_module = HybridRetrievalModule(PGV_module=PGV_DB,llm_client=DeepSeek_LLM)
        vectorRetriever = VectorRetriever(retrieval_module=retrieval_module)
        vector_result = await vectorRetriever.search(query=self.query)

        # 2.2 图遍历
        graph_traverser = GraphTraverser(extract_result=entity_result)
        graph_result = await graph_traverser.traverse()

        # 3. 对检索结果进行去重融合
        context_fusion_module = ContextFusionModule()


        # 4. 基于融合上下文生成结构化回答

        # 5. 将答案存入json

        return


        
    
