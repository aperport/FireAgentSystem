"""
图向量融合检索 — 实体扩散 + 子图文本化 + 向量精排。

核心思路：
    1. 从实体抽取结果出发，对每个实体在 Neo4j 中做两跳图遍历
    2. 将遍历得到的子图路径用连接词映射拼接为自然语言文本
    3. 对拼接文本做 Embedding，与用户问题向量做余弦相似度匹配
    4. 取 Top-K 作为最终图检索结果

与 GraphTraverser 的区别：
    GraphTraverser — 实体匹配 → 固定模板查询（结构驱动）
    GraphVectorTraverser — 实体扩散 → 向量精排（语义驱动）

对外接口：
    GraphVectorTraverser(query, extract_result, neo4j_driver, embedder).search() -> list[SubGraphResult]
"""

import os
from typing import Optional

import numpy as np
from langchain_core.embeddings import Embeddings
from langchain_huggingface import HuggingFaceEmbeddings
from neo4j import AsyncDriver

from graph_rag.config import get_settings
from graph_rag.entity_extractor import Entity, ExtractResult
from graph_rag.graph_db.connection import Neo4jDrivers
from graph_rag.graph_db.schema import REL_TYPES
from util_tools.logger import get_logger

logger = get_logger(__name__)

# 两跳遍历 Cypher：从实体名出发，不限节点类型和关系类型，遍历 1-2 跳
_TWO_HOP_CYPHER = """
MATCH (start {name: $entity_name})-[r1*1..2]-(end)
RETURN start, r1, end,
       [rel IN r1 | type(rel)] AS rel_types,
       [node IN r1 | labels(node)] AS node_labels
LIMIT $max_paths
"""

# 关系类型 → 自然语言连接词映射
_REL_CONNECTOR = {
    "包含功能": "包含功能",
    "操作步骤": "的操作步骤是",
    "下一步": "的下一步是",
    "前置条件": "的前置条件是",
    "包含条款": "包含条款",
    "引用": "引用了",
    "适用法规": "适用的法规是",
    "要求配置": "要求配置",
    "属于分类": "属于",
    "安装于": "安装在",
    "依赖": "依赖",
}


class SubGraphResult:
    """单条子图检索结果"""

    def __init__(self, text: str, score: float, path: list[dict], entity_name: str):
        self.text = text
        self.score = score
        self.path = path
        self.entity_name = entity_name

    def __repr__(self):
        return f"SubGraphResult(entity={self.entity_name}, score={self.score:.4f}, text={self.text[:60]}...)"


class GraphVectorTraverser:
    """
    图向量融合检索器。

    流程：实体抽取 → 两跳图遍历 → 子图文本化 → 向量相似度精排 → Top-K
    """

    def __init__(
        self,
        query: str,
        extract_result: ExtractResult,
        neo4j_driver: Neo4jDrivers,
        embedder: Optional[Embeddings] = None,
        top_k: int = 5,
        max_paths_per_entity: int = 20,
        score_threshold: float = 0.3,
    ):
        self.query = query
        self.extract_result = extract_result
        self.neo4j_driver = neo4j_driver
        self.top_k = top_k
        self.max_paths_per_entity = max_paths_per_entity
        self.score_threshold = score_threshold

        if embedder is None:
            s = get_settings()
            self.embedder = HuggingFaceEmbeddings(model_name=s.embedding_model_name,
                                                   model_kwargs={"device": s.embedding_device},
                                                   encode_kwargs={"normalize_embeddings": True})
        else:
            self.embedder = embedder

        self._query_embedding: Optional[list[float]] = None

    async def search(self) -> list[SubGraphResult]:
        """执行完整检索流程：遍历 → 文本化 → 精排"""
        driver = await self.neo4j_driver._get_async_driver()

        # 1. 两跳遍历，收集所有子图路径
        all_paths = await self._two_hop_traverse(driver)
        if not all_paths:
            logger.info("两跳遍历结果为空")
            return []

        # 2. 子图文本化
        subgraph_texts = self._paths_to_texts(all_paths)
        if not subgraph_texts:
            logger.info("子图文本化结果为空")
            return []

        # 3. 向量相似度精排
        results = self._rank_by_similarity(subgraph_texts)
        return results

    async def _two_hop_traverse(self, driver: AsyncDriver) -> list[dict]:
        """对每个实体做两跳遍历，收集所有路径"""
        all_paths = []
        for entity in self.extract_result.entities:
            if not entity or not entity.name:
                continue
            try:
                paths = await self._traverse_entity(driver, entity)
                all_paths.extend(paths)
            except Exception as e:
                logger.warning("实体 %s 两跳遍历失败: %s", entity.name, e)
        logger.info("两跳遍历完成，共 %d 条路径", len(all_paths))
        return all_paths

    async def _traverse_entity(self, driver: AsyncDriver, entity: Entity) -> list[dict]:
        """单个实体的两跳遍历"""
        async with driver.session(database=self.neo4j_driver.database) as session:
            result = await session.run(
                _TWO_HOP_CYPHER,
                {"entity_name": entity.name, "max_paths": self.max_paths_per_entity},
            )
            records = await result.data()

        paths = []
        for record in records:
            start_node = record.get("start")
            end_node = record.get("end")
            rel_types = record.get("rel_types", [])
            if start_node is None or end_node is None:
                continue
            paths.append({
                "entity_name": entity.name,
                "entity_type": entity.type,
                "start": dict(start_node) if start_node else {},
                "end": dict(end_node) if end_node else {},
                "rel_types": rel_types,
            })
        logger.debug("实体 %s 遍历到 %d 条路径", entity.name, len(paths))
        return paths

    def _paths_to_texts(self, paths: list[dict]) -> list[dict]:
        """将子图路径用连接词映射拼接为自然语言文本"""
        results = []
        seen_texts = set()

        for path in paths:
            entity_name = path["entity_name"]
            start_props = path["start"]
            end_props = path["end"]
            rel_types = path["rel_types"]

            start_name = start_props.get("name", str(start_props))
            end_name = end_props.get("name", str(end_props))

            # 用连接词映射拼接关系
            connectors = []
            for rt in rel_types:
                connector = _REL_CONNECTOR.get(rt, f"-[{rt}]->")
                connectors.append(connector)

            if connectors:
                text = f"{start_name} {connectors[0]} {end_name}"
            else:
                text = f"{start_name} 与 {end_name} 相关"

            # 去重
            if text in seen_texts:
                continue
            seen_texts.add(text)

            results.append({
                "text": text,
                "path": path,
                "entity_name": entity_name,
            })

        logger.info("子图文本化完成，去重后 %d 条", len(results))
        return results

    def _rank_by_similarity(self, subgraph_texts: list[dict]) -> list[SubGraphResult]:
        """向量相似度精排：对子图文本做 Embedding，与问题向量做余弦相似度"""
        if not subgraph_texts:
            return []

        # 问题 Embedding（只算一次）
        if self._query_embedding is None:
            self._query_embedding = self.embedder.embed_query(self.query)

        query_vec = np.array(self._query_embedding)

        # 子图文本 Embedding
        texts = [item["text"] for item in subgraph_texts]
        doc_embeddings = self.embedder.embed_documents(texts)

        # 余弦相似度
        results = []
        for item, doc_vec in zip(subgraph_texts, doc_embeddings):
            doc_arr = np.array(doc_vec)
            norm_product = np.linalg.norm(query_vec) * np.linalg.norm(doc_arr)
            if norm_product == 0:
                score = 0.0
            else:
                score = float(np.dot(query_vec, doc_arr) / norm_product)

            if score >= self.score_threshold:
                results.append(SubGraphResult(
                    text=item["text"],
                    score=score,
                    path=item["path"],
                    entity_name=item["entity_name"],
                ))

        # 按相似度降序排列，取 Top-K
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:self.top_k]

        logger.info("向量精排完成，%d 条结果超过阈值 %.2f，取 Top-%d", len(results), self.score_threshold, self.top_k)
        return results
