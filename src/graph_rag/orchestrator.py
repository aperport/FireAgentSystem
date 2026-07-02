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

⚠️ 已知问题：
    1. PG 连接参数硬编码（host="localhost", password=""），应从 config.py 读取
    2. 每次请求都重新创建 PGVectorManager / HybridRetrievalModule / GraphTraverser，
       应改为初始化时创建并复用
    3. 未接入 retrieval_evaluator.py 的空结果 fallback 机制

待实现：
    - 接入 retrieval_evaluator：向量/图检索为空时自动 fallback
    - 接入 config.py：消除硬编码连接参数
    - 单例复用：PGVectorManager / HybridRetrievalModule 等应只初始化一次
"""
from agent.llm_config import DeepSeek_LLM
from graph_rag.context_fusion import ContextFusionModule
from graph_rag.entity_extractor import EntityExtractor
from graph_rag.graph_traverser import GraphTraverser
from graph_rag.json_save import append_json_item
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


        
    
