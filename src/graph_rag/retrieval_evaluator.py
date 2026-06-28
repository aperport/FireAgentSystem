"""
检索结果评估模块 — 轻量兆底评分，决定是否升级检索策略。

与 evaluator.py 的区别：
    - evaluator.py：评估 LLM 生成的最终回答质量（RAGAS，需 LLM，慢，秒级）
    - 本模块：评估检索阶段的结果质量（启发式，零 LLM 调用，快，毫秒级）

设计理念：评估器是刹车不是方向盘。
只在近乎空结果时触发升级，其余情况信任检索结果交给 LLM 判断。
LLM 通过 hint 参数影响初始策略，评估器只做兆底保险。
"""

from dataclasses import dataclass
from util_tools.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalScore:
    """检索评分结果"""
    total_score: float          # 综合评分 0-1
    result_count_score: float   # 结果数量分 0-1
    similarity_score: float     # 最高相似度分 0-1（向量检索时有值）
    entity_coverage: float      # 实体覆盖率 0-1（图检索时有值）
    path_richness: float        # 路径丰富度 0-1（图检索时有值）
    should_upgrade: bool        # 是否需要升级查询
    reason: str                 # 评分说明（含各维度分数和升级原因）


class RetrievalEvaluator:
    """检索结果评估器

    对检索结果进行快速启发式评分，仅在结果极度不足时触发策略升级。
    评估维度：结果数量、相似度、实体覆盖率、路径丰富度，按策略权重加权汇总。
    """

    # 升级阈值：仅在近乎空结果时触发升级，避免过度干预 LLM 的策略选择
    UPGRADE_THRESHOLD: float = 0.25
    MAX_UPGRADES: int = 1

    # hint 参数 → 初始检索策略映射
    HINT_STRATEGY_MAP: dict[str, str] = {
        "simple":  "vector_first",
        "complex": "fusion",
        "explore": "graph_first",
        "auto":    "auto",
    }

    # 各检索类型的权重 (result_count, similarity, entity_coverage, path_richness)
    WEIGHTS: dict[str, tuple[float, float, float, float]] = {
        "vector": (0.2, 0.5, 0.0, 0.0),   # 向量检索：相似度为主
        "graph":  (0.2, 0.0, 0.4, 0.4),   # 图检索：覆盖率+路径为主
        "fusion": (0.2, 0.3, 0.2, 0.3),   # 融合检索：均衡
    }

    # 升级路径：当前策略 → 评分不足时升级到
    UPGRADE_PATH: dict[str, str] = {
        "vector_first": "fusion",
        "graph_first":  "fusion",
    }

    def choose_initial_strategy(
        self,
        hint: str,
        extract_result: 'ExtractResult',  # type: ignore  # 避免循环导入
    ) -> str:
        """根据 hint 和实体抽取结果选择初始检索策略

        Args:
            hint: LLM 传入的检索意图提示，可选 simple/complex/explore/auto
            extract_result: 实体抽取结果，hint="auto" 时用于自动判断策略

        Returns:
            初始检索策略名称：vector_first / graph_first / fusion
        """
        if hint not in self.HINT_STRATEGY_MAP:
            logger.warning("hint=%s 不在合法值中，回退为 auto", hint)
            hint = "auto"

        if hint != "auto":
            strategy = self.HINT_STRATEGY_MAP[hint]
            logger.info("hint=%s → 初始策略: %s", hint, strategy)
            return strategy

        # hint="auto"：根据实体抽取结果自动判断
        if not extract_result or not extract_result.entities:
            logger.info("hint=auto 且无实体抽取结果，默认 vector_first")
            return "vector_first"

        entity_types = {e.type.lower() for e in extract_result.entities if e.type}

        # 包含设备名/区域名/法规名 → 图遍历优先
        graph_types = {"equipment", "zonetype", "zone", "regulation", "clause", "standard"}
        if entity_types & graph_types:
            logger.info("hint=auto，实体类型含图节点类型 → graph_first")
            return "graph_first"

        # 多实体或含关系 → 融合检索
        if len(extract_result.entities) > 1 or (extract_result.relations and len(extract_result.relations) > 0):
            logger.info("hint=auto，多实体或含关系 → fusion")
            return "fusion"

        logger.info("hint=auto，单一简单实体 → vector_first")
        return "vector_first"

    def evaluate(
        self,
        results: list | None = None,
        graph_records: list[dict] | None = None,
        extract_result: 'ExtractResult | None' = None,
        strategy: str = "vector_first",
    ) -> RetrievalScore:
        """统一评估入口，轻量兆底判断

        核心逻辑：只在近乎空结果时才触发升级，其余情况信任检索结果交给 LLM 判断。
        - 向量侧：结果数量 + 最高相似度
        - 图侧：实体覆盖率 + 路径丰富度
        - 按当前策略的权重加权汇总

        Args:
            results: 向量检索返回的 Document 列表
            graph_records: 图遍历返回的 Record 列表
            extract_result: 实体抽取结果，用于计算覆盖率
            strategy: 当前检索策略，决定权重选择

        Returns:
            RetrievalScore 评估结果
        """
        # 确定权重
        if strategy in ("graph_first",) and not results:
            weight_key = "graph"
        elif strategy == "fusion" or (results and graph_records):
            weight_key = "fusion"
        else:
            weight_key = "vector"
        w = self.WEIGHTS[weight_key]

        # 向量侧指标
        vec_count = len(results) if results else 0
        result_count_score = min(vec_count / 3, 1.0)

        scores = []
        for doc in (results or []):
            s = doc.metadata.get("score", 0) if hasattr(doc, "metadata") else 0
            try:
                s = float(s)
            except (TypeError, ValueError):
                s = 0.0
            scores.append(s)
        max_sim = max(scores) if scores else 0.0
        similarity_score = min(max(max_sim, 0.0), 1.0)

        # 图侧指标
        entity_coverage_score = self._calc_entity_coverage(graph_records, extract_result)
        path_richness_score = self._calc_path_richness(graph_records)

        # 融合时结果数量合并计算
        if weight_key == "fusion":
            graph_count = len(graph_records) if graph_records else 0
            result_count_score = min((vec_count + graph_count) / 3, 1.0)

        total = (w[0] * result_count_score
                 + w[1] * similarity_score
                 + w[2] * entity_coverage_score
                 + w[3] * path_richness_score)

        should_upgrade = total < self.UPGRADE_THRESHOLD

        parts = [f"策略={strategy}({weight_key})", f"总分={total:.2f}"]
        if results is not None:
            parts.append(f"向量={vec_count}条/最高相似度={max_sim:.2f}")
        if graph_records is not None:
            parts.append(f"覆盖率={entity_coverage_score:.2f}/路径={path_richness_score:.2f}")
        parts.append("需升级" if should_upgrade else "达标")
        reason = ", ".join(parts)
        logger.info("检索评估: %s", reason)

        return RetrievalScore(
            total_score=total,
            result_count_score=result_count_score,
            similarity_score=similarity_score,
            entity_coverage=entity_coverage_score,
            path_richness=path_richness_score,
            should_upgrade=should_upgrade,
            reason=reason,
        )

    # ── 私有辅助 ──────────────────────────────────────────────────

    def _calc_entity_coverage(
        self,
        graph_records: list[dict] | None,
        extract_result: 'ExtractResult | None',
    ) -> float:
        """计算实体覆盖率：抽取实体中在图遍历结果里找到对应节点的比例"""
        if not extract_result or not extract_result.entities or not graph_records:
            return 0.0

        graph_names = set()
        for record in graph_records:
            if not isinstance(record, dict):
                continue
            for _key, node in record.items():
                if isinstance(node, dict) and "name" in node:
                    graph_names.add(node["name"].lower())

        found = sum(1 for e in extract_result.entities if e.name.lower() in graph_names)
        return found / max(len(extract_result.entities), 1)

    def _calc_path_richness(self, graph_records: list[dict] | None) -> float:
        """计算路径丰富度：min(paths_count / 3, 1.0)"""
        paths_count = len(graph_records) if graph_records else 0
        return min(paths_count / 3, 1.0)

    def get_upgrade_target(self, current_strategy: str, upgrade_count: int = 0) -> str | None:
        """获取升级目标策略，已达上限或无路径则返回 None"""
        if upgrade_count >= self.MAX_UPGRADES:
            logger.info("已达最大升级次数 %d，不再升级", self.MAX_UPGRADES)
            return None
        target = self.UPGRADE_PATH.get(current_strategy)
        if target:
            logger.info("策略升级: %s → %s (第 %d 次)", current_strategy, target, upgrade_count + 1)
        return target
