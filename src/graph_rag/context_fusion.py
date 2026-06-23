"""
上下文融合模块 — 将向量检索片段与图遍历路径合并为统一的融合上下文。

处理步骤：
    1. 实体去重：向量片段和图路径中可能包含相同实体的不同表述，需合并
    2. 相关性排序：按与查询的相关度排序（向量片段用score，图路径用跳数权重）
    3. 父文档回填：检索命中的子文档回填同一 source_hash 下的完整父文档内容
    4. Token截断：截断至 LLM 上下文窗口预算内，保留最相关的内容

融合策略：
    - 系统操作类问题：以图路径(步骤链)为主线，向量片段补充细节
    - 法规知识类问题：以向量片段(法规正文)为主线，图路径补充引用关系

由 orchestrator.py 调用。
"""
from langchain_core.documents import Document
from unitl_tools.logger import get_logger


logger = get_logger(__name__)


class ContextFusionModule:
    """上下文融合模块

    职责：
        - 父文档回填：将检索命中的子文档回填完整父文档内容
        - Token 预算截断：确保送入 LLM 的上下文不超出窗口
        - 实体去重与相关性排序（待实现）
    """

    @staticmethod
    def attach_parent_documents(
        chunks: list[Document],
        parent_map: dict[str, list[Document]],
        top_n: int = 3,
    ) -> list[Document]:
        """附加父文档内容

        将检索命中的子文档回填同一 source_hash 下的完整父文档内容,
        提供更丰富的上下文信息。

        Args:
            chunks: 检索命中的子文档
            parent_map: source_hash -> 同源子文档列表（由 db_retriever._build_parent_map() 构建）
            top_n: 只回填排名前 N 的文档，避免上下文过长

        Returns:
            list[Document]: 回填后的文档列表
        """
        if not parent_map:
            logger.warning("父文档映射表为空，无法回填父文档")
            return chunks

        top_chunks = chunks[:top_n]
        result: list[Document] = list(chunks)

        for chunk in top_chunks:
            source_hash = chunk.metadata.get("source_hash", "")
            if not source_hash or source_hash not in parent_map:
                continue

            # 获取同源的所有子文档，拼接为完整父文档内容
            sibling_docs = parent_map[source_hash]
            parent_content = "\n".join(doc.page_content for doc in sibling_docs)

            # 构建父文档，附加到结果末尾
            parent_doc = Document(
                page_content=parent_content,
                metadata={
                    "source_hash": source_hash,
                    "source_name": chunk.metadata.get("source_name", ""),
                    "category": chunk.metadata.get("category", ""),
                    "title": chunk.metadata.get("title", ""),
                    "parent_doc": True,
                    "child_count": len(sibling_docs),
                },
            )
            result.append(parent_doc)
            logger.info(
                f"父文档回填：source_hash={source_hash}，子文档数={len(sibling_docs)}"
            )

        return result

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """粗略估算 Token 数

        中文约 1.5 字/token，英文约 4 字符/token。
        采用简单启发式：中文按 1.5 字/token，其余按 4 字符/token。
        """
        chinese_chars = sum(1 for ch in text if '\u4e00' <= ch <= '\u9fff')
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)

    @classmethod
    def truncate_to_budget(cls, docs: list[Document], budget: int) -> list[Document]:
        """Token 预算截断

        按文档顺序（即相关性排序）依次累加 Token，超出预算时截断。
        优先保留排名靠前的高相关性文档，最后一份若超出预算则截断其内容。
        消防场景中法规条款、设备手册等文档较长，不做截断容易撑爆 LLM 上下文窗口。

        Args:
            docs: 待截断的文档列表（应已按相关性降序排列）
            budget: Token 预算上限

        Returns:
            list[Document]: 截断后的文档列表，总 Token 数不超过 budget
        """
        if budget <= 0 or not docs:
            return []

        result: list[Document] = []
        used_tokens = 0

        for doc in docs:
            doc_tokens = cls._estimate_tokens(doc.page_content)

            # 还能完整放下
            if used_tokens + doc_tokens <= budget:
                result.append(doc)
                used_tokens += doc_tokens
                continue

            # 放不下完整文档，但还有剩余预算 → 截断内容
            remaining = budget - used_tokens
            if remaining > 0:
                ratio = remaining / max(doc_tokens, 1)
                keep_chars = int(len(doc.page_content) * ratio)
                truncated_content = doc.page_content[:keep_chars] + "\n...[截断]"

                truncated_doc = Document(
                    page_content=truncated_content,
                    metadata={**doc.metadata, "truncated": True},
                )
                result.append(truncated_doc)
                used_tokens = budget

            # 预算用完，停止
            logger.info(
                f"Token 预算截断：已用 {used_tokens}/{budget}，"
                f"保留 {len(result)}/{len(docs)} 份文档"
            )
            break

        return result
