"""
规则辅助抽取模块 — 基于正则的实体补充抽取，与 LLM/NER 管道解耦。

当前实现：
    - extract_clause_numbers(): 从文本中用正则提取条款号，生成 Clause 类型实体

设计原则：
    - 规则抽取与 LLM/NER 无关，独立维护
    - 由编排层（entity_relation_extractor.py）调用，结果合并到 LLM+NER 融合结果中
    - 后续可扩展其他规则抽取器（如法规名正则、设备型号正则等）
"""

import re

from graph_rag.entity_extractor import Entity
from util_tools.logger import get_logger

logger = get_logger(__name__)


# ===================== 条款号正则模式 =====================
# 按优先级排列：最具体的模式在前，避免被宽泛模式提前匹配
# 例如 "第一条第一款" 应被第1个模式匹配，而非被第4个"第一条" 匹配
CLAUSE_PATTERNS: list[re.Pattern] = [
    # 第X条第X款（中文数字）
    re.compile(r"第[一二三四五六七八九十百千万]+条第[一二三四五六七八九十百]+款"),
    # 第X条第X款（阿拉伯数字）
    re.compile(r"第\d+条第\d+款"),
    # X.X.X节 / X.X.X条（阿拉伯数字点号，如 5.1.1节、5.1.1条）
    re.compile(r"\d+\.\d+(?:\.\d+)?(?:节|条)"),
    # X.X节（两位版本，如 5.1节）
    re.compile(r"\d+\.\d+节"),
    # 第X条（中文数字）
    re.compile(r"第[一二三四五六七八九十百千万]+条"),
    # 第X条（阿拉伯数字）
    re.compile(r"第\d+条"),
]


def extract_clause_numbers(text: str) -> list[Entity]:
    """从文本中用正则提取条款号，生成 Clause 类型实体。

    识别模式（按优先级排列）：
        - 第X条第X款（中文数字）：如"第一条第一款"
        - 第X条第X款（阿拉伯数字）：如 "第1条第2款"
        - X.X.X节 / X.X.X条：如"5.1.1节"、"5.1.1条"
        - X.X节：如"5.1节"
        - 第X条（中文数字）：如"第一条"
        - 第X条（阿拉伯数字）：如 "第1条"

    返回的 Entity.type 固定为 "Clause"，
    Entity.name 为匹配到的原始条款号文本。

    Args:
        text: 文档段落文本

    Returns:
        提取到的条款号实体列表（去重后）
    """
    seen = set()
    entities = []

    for pattern in CLAUSE_PATTERNS:
        for match in pattern.finditer(text):
            clause_name = match.group()
            if clause_name not in seen:
                seen.add(clause_name)
                entities.append(Entity(name=clause_name, type="Clause"))

    if entities:
        logger.debug(f"规则辅助抽取: 从文本中提取到 {len(entities)} 个条款号")

    return entities
