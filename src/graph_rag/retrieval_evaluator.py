"""
检索结果判空模块 — 结果为空或极低质量时自动 fallback 到其他检索工具。

与 evaluator.py 的区别：
    - evaluator.py：评估 LLM 最终回答质量（RAGAS，需 LLM，慢）
    - 本模块：检索后快速判空，空结果自动补查（纯算术，毫秒级）

工具内部调用，对 LLM 不可见。LLM 觉得不够会自己追查，这里只处理“查空了”的情况。
"""

from dataclasses import dataclass
from graph_rag.entity_extractor import ExtractResult
from util_tools.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalCheck:
    """检索判空结果"""
    need_fallback: bool          # 是否需要 fallback
    fallback_target: str | None  # fallback 目标工具名，无则 None
    reason: str                  # 判断说明


class RetrievalEvaluator:
    """检索结果判空器

    检索工具内部调用，对 LLM 不可见。
    判断结果是否为空/极低质量，决定是否自动补查到其他工具。
    """

    # fallback 路径
    FALLBACK_MAP: dict[str, str] = {
        "knowledge_search": "graph_rag_search",   # 向量查不到 → 补融合
        "graph_query": "graph_rag_search",         # 图查不到 → 补融合
    }

    # 向量检索最低相似度，低于此值视为无效
    MIN_SIMILARITY: float = 0.3

    def check_vector(
        self,
        results: list,         # list[Document]
        source_tool: str = "knowledge_search",
    ) -> RetrievalCheck:
        """判断向量检索结果是否需要 fallback

        触发条件：0 条结果，或少于 3 条且最高相似度 < MIN_SIMILARITY
        """
        count = len(results) if results else 0

        if count == 0:
            fallback = self.FALLBACK_MAP.get(source_tool)
            reason = f"向量检索返回 0 条结果，需 fallback 到 {fallback}"
            logger.info(reason)
            return RetrievalCheck(need_fallback=True, fallback_target=fallback, reason=reason)

        # 提取最高相似度
        max_sim = 0.0
        for doc in results:
            s = doc.metadata.get("score", 0) if hasattr(doc, "metadata") else 0
            try:
                s = float(s)
            except (TypeError, ValueError):
                s = 0.0
            if s > max_sim:
                max_sim = s

        if count <= 2 and max_sim < self.MIN_SIMILARITY:
            fallback = self.FALLBACK_MAP.get(source_tool)
            reason = f"向量检索仅 {count} 条且最高相似度={max_sim:.2f} < {self.MIN_SIMILARITY}，需 fallback 到 {fallback}"
            logger.info(reason)
            return RetrievalCheck(need_fallback=True, fallback_target=fallback, reason=reason)

        logger.info("向量检索结果充足: %d 条, 最高相似度=%.2f", count, max_sim)
        return RetrievalCheck(need_fallback=False, fallback_target=None, reason="结果充足")

    def check_graph(
        self,
        graph_records: list[dict],
        extract_result: 'ExtractResult | None' = None,
        source_tool: str = "graph_query",
    ) -> RetrievalCheck:
        """判断图遍历结果是否需要 fallback

        触发条件：0 条记录，或实体覆盖率为 0（抽取的实体全没匹配到）
        """
        count = len(graph_records) if graph_records else 0

        if count == 0:
            fallback = self.FALLBACK_MAP.get(source_tool)
            reason = f"图遍历返回 0 条记录，需 fallback 到 {fallback}"
            logger.info(reason)
            return RetrievalCheck(need_fallback=True, fallback_target=fallback, reason=reason)

        # 有实体抽取结果时，检查覆盖率
        if extract_result and extract_result.entities:
            graph_names = set()
            for record in graph_records:
                if not isinstance(record, dict):
                    continue
                for _key, node in record.items():
                    if isinstance(node, dict) and "name" in node:
                        graph_names.add(node["name"].lower())

            found = sum(1 for e in extract_result.entities if e.name.lower() in graph_names)
            coverage = found / max(len(extract_result.entities), 1)

            if coverage == 0:
                fallback = self.FALLBACK_MAP.get(source_tool)
                reason = f"图遍历 {count} 条记录但实体覆盖率为 0，需 fallback 到 {fallback}"
                logger.info(reason)
                return RetrievalCheck(need_fallback=True, fallback_target=fallback, reason=reason)

        logger.info("图遍历结果充足: %d 条记录", count)
        return RetrievalCheck(need_fallback=False, fallback_target=None, reason="结果充足")

    def check_fusion(
        self,
        vector_results: list | None = None,
        graph_records: list[dict] | None = None,
    ) -> RetrievalCheck:
        """判断融合检索结果是否需要 fallback

        融合已是最强策略，不再 fallback，只记录结果状态。
        """
        vec_count = len(vector_results) if vector_results else 0
        graph_count = len(graph_records) if graph_records else 0
        total = vec_count + graph_count

        if total == 0:
            reason = "融合检索向量+图均为空，无可 fallback 目标"
            logger.warning(reason)
            return RetrievalCheck(need_fallback=False, fallback_target=None, reason=reason)

        logger.info("融合检索结果: 向量=%d条, 图=%d条", vec_count, graph_count)
        return RetrievalCheck(need_fallback=False, fallback_target=None, reason="结果充足")
