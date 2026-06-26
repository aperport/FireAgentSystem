"""
检索结果评估模块 — 对检索结果进行快速评分，决定是否升级查询策略。

与 evaluator.py 的区别：
    - evaluator.py：评估 LLM 生成的最终回答质量（RAGAS，需 LLM，慢，秒级）
    - 本模块：评估检索阶段的结果质量（启发式，零 LLM 调用，快，毫秒级）

设计理念 — LLM 建议 + 评估兜底：
    LLM 和评估系统判断的层面不同，两者互补而非替代：
        - LLM 擅长：检索前的意图理解（"该查什么方向？"）
        - 评估系统擅长：检索后的质量验证（"查到的够不够？"）

    因此采用"LLM 传 hint 建议 + 评估系统硬性兜底"的双保险机制：
        - hint 是 LLM 的"建议"，影响初始检索策略
        - 评估系统是代码的"否决权"，LLM 建议错了，代码能救
        - LLM 不传 hint，默认 auto 也能跑

hint 参数与初始策略的映射：
    ┌──────────┬──────────────────────────────────────────────┐
    │ hint 值   │ 初始检索策略                                  │
    ├──────────┼──────────────────────────────────────────────┤
    │ simple   │ 向量检索优先（适合单一事实/定义/分类问题）       │
    │ complex  │ 融合检索优先（适合关联/多文档/法规引用链问题）   │
    │ explore  │ 图遍历优先（适合已知起点深度探索问题）           │
    │ auto     │ 由实体抽取结果自动决定（默认值）                │
    └──────────┴──────────────────────────────────────────────┘

    hint 选择规则（写入子 Agent system_prompt 引导 LLM）：
        - 问题中包含具体设备名/区域名/法规名 → 优先选 explore
        - 问题涉及"哪些要求""什么关系""如何关联" → 选 complex
        - 问题只需一个直接答案 → 选 simple
        - 拿不准 → 选 auto

    强制传参机制：
        1. 工具参数定义（硬约束）：hint 为枚举类型，LLM 只能从四个值中选
        2. 提示词引导（软约束）：system_prompt 中明确 hint 选择规则

评估时机：
    每次检索工具返回结果后，在升级决策前调用。
    评估发生在"格式化给 LLM"之前——决定"这批结果够不够好，要不要换策略重查"，
    而不是"内容对不对"。

评估的数据来源 — 评估系统不看文本内容，只看统计指标：
    ┌─────────────────────────────────────────────────────────────────┐
    │                    向量检索返回 list[Document]                    │
    │  Document(                                                      │
    │      page_content="第5.1.1条 高层建筑的耐火等级应为一级...",      │
    │      metadata={                                                 │
    │          "id": 123,                                             │
    │          "category": "regulation",                              │
    │          "score": 0.87,  ← 评估系统用这个（相似度）              │
    │          "search_type": "dense",                                │
    │      }                                                          │
    │  )                                                              │
    │  评估系统提取：len(results) → 结果数量, max(score) → 最高相似度  │
    └─────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────┐
    │                  图遍历返回 Neo4j Record 列表                     │
    │  {                                                              │
    │      "module": {"name": "消防巡检", "description": "..."},       │
    │      "function": {"name": "日常巡检", "description": "..."},     │
    │      "step": {"name": "检查烟感", "step_order": 1},             │
    │      "precondition": {"name": "巡检资质", "description": "..."}, │
    │  }                                                              │
    │  评估系统提取：匹配到的实体数 → 实体覆盖率, 路径数 → 路径丰富度  │
    │  注意：图遍历没有 score 字段，相似度维度为 0（由其他维度补偿）    │
    └─────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────┐
    │                  融合检索 = 向量结果 + 图遍历结果                 │
    │  评估系统同时提取两类指标，按融合权重计算综合分                    │
    └─────────────────────────────────────────────────────────────────┘

    关键区别：
        - 评估系统：只看数字指标（数量、分数、覆盖率、路径数），毫秒级
        - context_fusion.py：看文本内容，格式化+去重+截断，拼成一段文本给 LLM
        - 评估在融合之前，融合在评估之后

完整数据流：
    检索结果 ──→ 评估系统（只看数字指标，毫秒级）──→ 评分低？升级重查
        │
        │ 评分OK
        ▼
    context_fusion.py（格式化+融合+Token截断）──→ 拼成一段文本 ──→ 给 LLM

评估维度（四个信号，加权汇总）：
    1. 结果数量（result_count）：
       - 0 条结果 → 0 分，说明完全没命中
       - 1-2 条 → 偏低，可能不够充分
       - 3+ 条 → 正常，信息量充足
       评分公式：min(count / (top_k * 0.6), 1.0)

    2. 最高相似度（max_similarity）：
       - 向量检索自带 score，直接使用
       - 图遍历无 score，此项为 0（由其他维度补偿）
       评分公式：score 归一化到 0-1

    3. 实体覆盖率（entity_coverage）：
       - 抽取的实体中，有多少在图遍历结果中找到了对应节点
       - 仅图检索时有值，向量检索时为 0
       评分公式：found_count / total_count

    4. 路径丰富度（path_richness）：
       - 图遍历返回了多少条关联路径
       - 3 条以上算满分，少于 3 条按比例
       - 仅图检索时有值，向量检索时为 0
       评分公式：min(paths_count / 3, 1.0)

综合评分公式：
    total = w1 * result_count_score
          + w2 * max_similarity_score
          + w3 * entity_coverage_score
          + w4 * path_richness_score

各检索类型权重不同：
    - 向量检索 (vector)： (0.2, 0.5, 0.0, 0.0) — 相似度为主
    - 图检索   (graph)：  (0.2, 0.0, 0.4, 0.4) — 覆盖率+路径为主
    - 融合检索 (fusion)： (0.2, 0.3, 0.2, 0.3) — 均衡

完整检索流程（smart_search 内部编排）：
    用户问题
        │
        ▼
    LLM 调用 smart_search(query, hint="complex")
        │
        ▼
    ┌─────────────────────────────────────────────────┐
    │ 1. 实体抽取                                      │
    │    extract_result = extractor.main_pip()          │
    │                                                   │
    │ 2. 初始策略选择（hint + 实体抽取结果 共同决定）     │
    │    hint="simple"  → 向量检索优先                   │
    │    hint="complex" → 融合检索优先                   │
    │    hint="explore" → 图遍历优先                     │
    │    hint="auto"    → 实体抽取结果决定               │
    │                                                   │
    │ 3. 执行初始检索                                    │
    │    result = search(strategy)                       │
    │                                                   │
    │ 4. 评估（强制，每次都执行，LLM 无法跳过）           │
    │    score = evaluator.evaluate()                    │
    │                                                   │
    │ 5. 评分低 → 自动升级                               │
    │    while score.should_upgrade:                     │
    │        upgrade_strategy()                          │
    │        result = search(new_strategy)               │
    │        score = evaluator.evaluate()                │
    │                                                   │
    │ 6. 返回最终结果                                    │
    └─────────────────────────────────────────────────┘

升级策略（评分低于阈值时触发）：
    ┌──────────────────┐     score < 0.5     ┌──────────────────┐
    │ knowledge_search │ ──────────────────→ │ graph_rag_search │
    │   (纯向量检索)    │                     │  (向量+图融合)    │
    └──────────────────┘                     └──────────────────┘
                                                      │
                                              score < 0.5
                                                      │
                                                      ▼
                                              ┌──────────────┐
                                              │  内部三级降级  │
                                              │ 模板→图反查→  │
                                              │ LLM生成Cypher │
                                              └──────────────┘

    ┌──────────────────┐     score < 0.5     ┌──────────────────┐
    │   graph_query    │ ──────────────────→ │ graph_rag_search │
    │   (纯图遍历)      │                     │  (向量+图融合)    │
    └──────────────────┘                     └──────────────────┘

    ┌──────────────────┐     score < 0.5     ┌──────────────┐
    │ graph_rag_search │ ──────────────────→ │  graph_query │
    │  (向量+图融合)    │                     │  (补充图关联) │
    └──────────────────┘                     └──────────────┘

升级上限：
    - 最多升级 2 次，防止无限循环
    - 已是最高级工具且评分仍低 → 返回已有结果 + 低分提示

调用方：
    - smart_search MCP Tool（唯一对外入口）
    - orchestrator.py 编排流程中

由 smart_search 和 orchestrator.py 调用。
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

    职责：
        - 对检索结果进行快速启发式评分
        - 判断是否需要升级到更强的检索策略
        - 记录评分日志，供后续调优权重和阈值
        - 根据 hint 参数调整初始策略权重

    hint 参数与评估的关系：
        hint 是 LLM 传入的检索意图建议，影响初始策略选择：
            - hint="simple"  → 向量检索优先，评估侧重 similarity_score
            - hint="complex" → 融合检索优先，评估侧重全维度均衡
            - hint="explore" → 图遍历优先，评估侧重 entity_coverage + path_richness
            - hint="auto"    → 实体抽取结果决定策略，评估按实际检索类型选权重

        评估系统对 hint 有"否决权"：
            - LLM 传 hint="simple" 但向量检索评分低 → 自动升级到融合检索
            - LLM 传 hint="explore" 但图遍历评分低 → 自动升级到融合检索
            - hint 只影响初始策略，评估系统保证最终结果质量

    使用方式：
        evaluator = RetrievalEvaluator()
        score = evaluator.evaluate_vector(results, top_k=5)
        if score.should_upgrade:
            # 升级到 graph_rag_search
            ...
    """

    # 升级阈值：低于此分数触发升级
    UPGRADE_THRESHOLD: float = 0.5

    # hint 参数 → 初始检索策略映射
    HINT_STRATEGY_MAP: dict[str, str] = {
        "simple":  "vector_first",    # 向量检索优先
        "complex": "fusion",          # 融合检索优先
        "explore": "graph_first",     # 图遍历优先
        "auto":    "auto",            # 由实体抽取结果决定
    }

    # 各检索类型的权重 (result_count, similarity, entity_coverage, path_richness)
    WEIGHTS: dict[str, tuple[float, float, float, float]] = {
        "vector": (0.2, 0.5, 0.0, 0.0),   # 向量检索：相似度为主
        "graph":  (0.2, 0.0, 0.4, 0.4),   # 图检索：覆盖率+路径为主
        "fusion": (0.2, 0.3, 0.2, 0.3),   # 融合检索：均衡
    }

    # 升级路径：当前策略 → 评分不足时升级到
    UPGRADE_PATH: dict[str, str] = {
        "vector_first": "fusion",       # 向量不够 → 升级到融合
        "graph_first":  "fusion",       # 图不够 → 升级到融合
        "fusion":       "graph_first",  # 融合不够 → 补充纯图关联
    }

    # 最大升级次数，防止无限循环
    MAX_UPGRADES: int = 2

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
        # TODO: 实现初始策略选择逻辑
        ...

    def evaluate_vector(
        self,
        results: list,  # list[Document]，向量检索返回的 LangChain Document 列表
        top_k: int = 5,
        hint: str = "simple",
    ) -> RetrievalScore:
        """评估向量检索结果

        数据来源：向量检索返回 list[Document]
            - 每条 Document.metadata["score"] 提供相似度分数
            - len(results) 提供结果数量
            - 图检索维度（entity_coverage, path_richness）为 0

        Args:
            results: 向量检索返回的 Document 列表，每项 metadata 需含 score 字段
            top_k: 请求的返回条数
            hint: LLM 传入的检索意图，影响权重选择

        Returns:
            RetrievalScore 评分结果
        """
        # TODO: 实现向量检索评估逻辑
        ...

    def evaluate_graph(
        self,
        graph_records: list[dict],  # Neo4j Record 列表，图遍历返回的结构化节点属性
        extract_result: 'ExtractResult | None' = None,  # 实体抽取结果，用于计算覆盖率
        hint: str = "explore",
    ) -> RetrievalScore:
        """评估图遍历结果

        数据来源：图遍历返回 Neo4j Record 列表
            - 每条 Record 是节点属性字典 {"name": ..., "description": ...}
            - 没有 score 字段，相似度维度为 0
            - 通过匹配 extract_result.entities 与 Record 中的节点计算覆盖率
            - 通过统计 Record 中不同路径的数量计算路径丰富度

        Args:
            graph_records: 图遍历返回的 Record 列表，每项为节点属性字典
            extract_result: 实体抽取结果，用于计算实体覆盖率（found/total）
            hint: LLM 传入的检索意图，影响权重选择

        Returns:
            RetrievalScore 评分结果
        """
        # TODO: 实现图遍历评估逻辑
        ...

    def evaluate_fusion(
        self,
        vector_results: list,  # list[Document]，向量检索结果
        graph_records: list[dict],  # Neo4j Record 列表，图遍历结果
        extract_result: 'ExtractResult | None' = None,  # 实体抽取结果，用于计算覆盖率
        hint: str = "complex",
    ) -> RetrievalScore:
        """评估融合检索结果（向量+图）

        数据来源：向量检索 list[Document] + 图遍历 list[Record]
            - 向量侧：len(results) + max(score) → 结果数量 + 相似度
            - 图侧：匹配实体数/总实体数 + 路径数 → 覆盖率 + 路径丰富度
            - 融合权重均衡分配四个维度

        Args:
            vector_results: 向量检索返回的 Document 列表
            graph_records: 图遍历返回的 Record 列表
            extract_result: 实体抽取结果，用于计算实体覆盖率
            hint: LLM 传入的检索意图，影响权重选择

        Returns:
            RetrievalScore 评分结果
        """
        # TODO: 实现融合检索评估逻辑
        ...

    def get_upgrade_target(self, current_strategy: str, upgrade_count: int = 0) -> str | None:
        """获取升级目标策略

        Args:
            current_strategy: 当前使用的检索策略名称
            upgrade_count: 已升级次数

        Returns:
            升级目标策略名称，已达上限则返回 None
        """
        # TODO: 实现升级路径判断逻辑
        ...
