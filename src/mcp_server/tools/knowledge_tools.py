"""
知识检索 MCP 工具 — 为 fire-qa-assistant 子智能体提供 GraphRAG 检索能力。

注册三个 MCP Tool：
    1. graph_rag_search  — 高层组合：向量检索+图遍历+融合，一键返回完整上下文
    2. knowledge_search  — 底层原子：纯向量检索（简单问答直接用）
    3. graph_query       — 底层原子：纯图查询（已知起点做深度遍历）

工具选择策略（由子智能体 system_prompt 引导）：
    - 简单问题（单文档/单条款）→ knowledge_search
    - 复杂关联（跨文档/法规引用链）→ graph_rag_search
    - 已知起点深度遍历（追踪某法规所有引用）→ graph_query

graph_query 同时被 fire-management-analyst 复用，限定用于故障影响链分析。

当前已接入真实 GraphRAG（orchestrator.py / VectorRetriever / GraphTraverser），
不再使用 Mock 数据。
"""

import asyncio
import sys
import os

from fastmcp import FastMCP

# ponytail: 确保 graph_rag 模块可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# [修改] 不再导入已删除的 VectorQuery / GraphQuery，改为直接使用底层组件
from graph_rag.orchestrator import GraphRAGOrchestrator, _BM25Index, _Neo4jDriver
from graph_rag.entity_extractor import EntityExtractor
from graph_rag.vector_retriever import VectorRetriever
from graph_rag.graph_traverser import GraphTraverser
from agent.llm_config import DeepSeek_LLM
from util_tools.logger import get_logger

logger = get_logger(__name__)


def register_knowledge_tools(mcp: FastMCP):
    """注册知识检索工具到 MCP Server"""

    @mcp.tool(name="graph_rag_search")
    async def graph_rag_search(
        query: str,
        top_k: int = 5,
    ) -> dict:
        """
        GraphRAG组合检索：向量检索+图遍历+融合，一键返回完整上下文。
        适用于复杂关联问题（跨文档/法规引用链/设备依赖链）。

        Args:
            query: 检索问题，如"ICU病房消防系统要满足哪些要求"
            top_k: 返回结果数量上限，默认5
        Returns:
            检索结果，包含 answer、sources、score、status
        """
        logger.info("graph_rag_search 调用: query=%s", query)
        try:
            orchestrator = GraphRAGOrchestrator(query=query)
            result = await orchestrator.rag_search(top_k=top_k)
            logger.info("graph_rag_search 完成: %d 条结果", len(result))
            return {
                "answer": "\n\n".join([doc.page_content for doc in result[:3]]),
                "sources": [
                    {
                        "type": "document",
                        "title": doc.metadata.get("title", ""),
                        "source_file": doc.metadata.get("source_file", ""),
                        "score": doc.metadata.get("score", 0),
                    }
                    for doc in result[:3]
                ],
                "total": len(result),
                "status": "success",
            }
        except Exception as e:
            logger.error("graph_rag_search 失败: %s", e, exc_info=True)
            return {
                "answer": "",
                "sources": [],
                "total": 0,
                "status": f"error: {e}",
            }

    @mcp.tool(name="knowledge_search")
    async def knowledge_search(
        query: str,
        max_results: int = 5,
    ) -> dict:
        """
        纯向量检索。适用于简单问题（单文档/单条款可直接回答）。
        复杂关联问题应使用 graph_rag_search。

        Args:
            query: 检索问题
            max_results: 返回结果数量上限，默认5

        Returns:
            检索结果列表，包含 answer、source、score
        """
        logger.info("knowledge_search 调用: query=%s", query)
        try:
            # [修改] 原先使用 VectorQuery 类（已删除），现直接调用底层 VectorRetriever
            retrieval_module = _BM25Index.get()
            vector_retriever = VectorRetriever(retrieval_module=retrieval_module)
            result = await vector_retriever.search(query=query)
            logger.info("knowledge_search 完成: %d 条结果", len(result))
            return {
                "total": len(result),
                "items": [
                    {
                        "answer": doc.page_content,
                        "source": doc.metadata.get("source_file", ""),
                        "score": doc.metadata.get("score", 0),
                    }
                    for doc in result[:max_results]
                ],
                "status": "success",
            }
        except Exception as e:
            logger.error("knowledge_search 失败: %s", e, exc_info=True)
            return {
                "total": 0,
                "items": [],
                "status": f"error: {e}",
            }

    @mcp.tool(name="graph_query")
    async def graph_query(
        entity: str,
    ) -> dict:
        """
        纯图遍历查询。适用于已知起点做深度遍历（追踪某法规所有引用/故障影响链分析）。
        常规数据查询应走 MCP 明细工具。

        Args:
            entity: 起始实体名称，如"EPS电源-01"、"ICU病房"

        Returns:
            图遍历结果，包含 paths 路径列表、entities 关联实体、total_paths
        """
        logger.info("graph_query 调用: entity=%s", entity)
        try:
            # [修改] 原先使用 GraphQuery 类（已删除），现直接调用底层 EntityExtractor + GraphTraverser
            entity_extractor = EntityExtractor(llm_client=DeepSeek_LLM, query=entity)
            entity_result = await entity_extractor.main_pip()
            graph_traverser = _Neo4jDriver.get()
            graph_traverser.extract_result = entity_result
            result = await graph_traverser.traverse()
            logger.info("graph_query 完成: %d 条路径", len(result))
            return {
                "paths": result,
                "entities": [],
                "total_paths": len(result),
                "status": "success",
            }
        except Exception as e:
            logger.error("graph_query 失败: %s", e, exc_info=True)
            return {
                "paths": [],
                "entities": [],
                "total_paths": 0,
                "status": f"error: {e}",
            }
