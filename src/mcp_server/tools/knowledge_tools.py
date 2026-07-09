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

当前已接入真实 GraphRAG（orchestrator.py / VectorQuery / GraphQuery），
不再使用 Mock 数据。
"""

import asyncio
import sys
import os

from fastmcp import FastMCP

# ponytail: 确保 graph_rag 模块可导入
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from graph_rag.orchestrator import GraphRAGOrchestrator, VectorQuery, GraphQuery
from util_tools.logger import get_logger

logger = get_logger(__name__)


def register_knowledge_tools(mcp: FastMCP):
    """注册知识检索工具到 MCP Server"""

    @mcp.tool(name="graph_rag_search")
    async def graph_rag_search(
        query: str,
        search_type: str = "hybrid",
        max_vector_results: int = 5,
        graph_depth: int = 2,
        score_threshold: float = 0.7,
    ) -> dict:
        """
        GraphRAG组合检索：向量检索+图遍历+融合，一键返回完整上下文。
        适用于复杂关联问题（跨文档/法规引用链/设备依赖链）。

        Args:
            query: 检索问题，如"ICU病房消防系统要满足哪些要求"
            search_type: 检索类型，可选：hybrid(默认)/vector_only/graph_only
            max_vector_results: 向量检索结果数量上限，默认5
            graph_depth: 图遍历深度，默认2
            score_threshold: 相似度阈值，默认0.7

        Returns:
            检索结果，包含 answer、sources、score、status
        """
        logger.info("graph_rag_search 调用: query=%s", query)
        try:
            orchestrator = GraphRAGOrchestrator(query=query)
            result = await orchestrator.rag_search()
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
        score_threshold: float = 0.7,
    ) -> dict:
        """
        纯向量检索。适用于简单问题（单文档/单条款可直接回答）。
        复杂关联问题应使用 graph_rag_search。

        Args:
            query: 检索问题
            max_results: 返回结果数量上限，默认5
            score_threshold: 相似度阈值，默认0.7

        Returns:
            检索结果列表，包含 answer、source、score
        """
        logger.info("knowledge_search 调用: query=%s", query)
        try:
            vq = VectorQuery(query=query)
            result = await vq.vector_query()
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
        relation_types: list[str] | None = None,
        depth: int = 2,
        direction: str = "outgoing",
    ) -> dict:
        """
        纯图遍历查询。适用于已知起点做深度遍历（追踪某法规所有引用/故障影响链分析）。
        常规数据查询应走 MCP 明细工具。

        Args:
            entity: 起始实体名称，如"EPS电源-01"、"ICU病房"
            relation_types: 限定关系类型，如["依赖","安装于"]，为空则遍历所有关系
            depth: 遍历深度，默认2
            direction: 遍历方向，可选：outgoing(默认)/incoming/both

        Returns:
            图遍历结果，包含 paths 路径列表、entities 关联实体、total_paths
        """
        logger.info("graph_query 调用: entity=%s", entity)
        try:
            gq = GraphQuery(query=entity)
            result = await gq.graph_query()
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
