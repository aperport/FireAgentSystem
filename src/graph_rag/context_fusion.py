"""
上下文融合模块 — 将向量检索片段与图遍历路径合并为统一的融合上下文。

✅ 已实现。处理步骤：
    0. 图记录转换：Neo4j Cypher 记录 → LangChain Document（graph_records_to_documents）
    1. 实体去重：向量片段和图路径中可能包含相同实体的不同表述，需合并
    2. 相关性排序：按与查询的相关度排序（向量片段用score，图路径用跳数权重）
    3. 父文档回填：检索命中的子文档回填同一 source_file 下的完整父文档内容
    4. Token截断：截断至 LLM 上下文窗口预算内，保留最相关的内容

融合策略（当前实现）：
    - 所有文档统一按 rrf_score > score > hop_weight 排序，不区分问题类型
    - 原计划按问题类型切换策略（系统操作以图为主，法规以向量为主），尚未实现

由 orchestrator.py 调用（fuse() 方法为异步管线入口）。

待优化：
    1. 按问题类型切换融合策略：系统操作类以图路径为主线，法规类以向量片段为主线
    2. _estimate_tokens() 为粗略估算，可替换为 tiktoken 精确计算
    3. 中文 Unicode 范围 '一'~'鿿' 不完整，应扩展到 CJK 统一表意文字区块
"""
import asyncio
import hashlib
from langchain_core.documents import Document
from util_tools.logger import get_logger


logger = get_logger(__name__)


class ContextFusionModule:
    """上下文融合模块

    职责：
        - 实体去重：合并向量片段与图路径中的重复内容
        - 相关性排序：按综合相关度降序排列
        - 父文档回填：将检索命中的子文档回填完整父文档内容
        - Token 预算截断：确保送入 LLM 的上下文不超出窗口
    """

    def __init__(self, parent_map: dict[str, list[Document]] | None = None):
        """初始化上下文融合模块

        Args:
            parent_map: source_file -> 同源子文档列表，
                由 HybridRetrievalModule._build_parent_map() 构建，
                可后续通过 set_parent_map() 更新。
        """
        self._parent_map: dict[str, list[Document]] = parent_map or {}

    def set_parent_map(self, parent_map: dict[str, list[Document]]) -> None:
        """更新父文档映射表

        在检索模块重新加载/重建索引后调用，同步最新的 parent_map。

        Args:
            parent_map: source_file -> 同源子文档列表
        """
        self._parent_map = parent_map
        logger.info(f"父文档映射表已更新，条目数={len(parent_map)}")

    @property
    def parent_map(self) -> dict[str, list[Document]]:
        """当前父文档映射表"""
        return self._parent_map

    # ────────────────────── 0. 图记录转 Document ──────────────────────

    @staticmethod
    def graph_records_to_documents(
        records: list[dict] | None,
        hop_count: int = 1,
    ) -> list[Document]:
        """将 Neo4j Cypher 查询记录转为 Document 列表

        Neo4j session.run().data() 返回 list[dict]，每条 dict 的 key 是
        Cypher RETURN 中的变量名（如 module, function, step），value 是
        节点属性字典（如 {"name": "值班", "description": "..."}）或 None。

        转换策略：
            - 每条 record 中非 None 的节点各生成一个 Document
            - page_content：将节点属性格式化为 "键: 值" 的可读文本
            - metadata：记录节点标签、节点名、跳数权重、检索来源等，
              供后续去重和排序使用

        示例输入（系统操作导航）：
            [
                {"module": {"name": "值班", "description": "值班管理"},
                 "function": {"name": "交接班"}, "step": None, "requirement": None},
                ...
            ]

        示例输出：
            [
                Document(page_content="name: 值班\ndescription: 值班管理",
                         metadata={"node_label": "Module", "node_name": "值班",
                                   "hop_count": 1, "search_type": "graph"}),
                Document(page_content="name: 交接班",
                         metadata={"node_label": "Function", "node_name": "交接班",
                                   "hop_count": 1, "search_type": "graph"}),
                ...
            ]

        Args:
            records: Neo4j 查询返回的记录列表，每条为 {变量名: 节点属性dict | None}
            hop_count: 图遍历跳数，默认 1，影响排序权重（跳数越少权重越高）

        Returns:
            list[Document]: 转换后的文档列表
        """
        if not records:
            return []

        # 节点变量名 → 标签映射（与 GraphQueries 中的 RETURN 变量名对应）
        _LABEL_MAP: dict[str, str] = {
            # 系统操作子图
            "module": "Module",
            "function": "Function",
            "step": "Step",
            "requirement": "Requirement",
            # 法规关联子图
            "regulation": "Regulation",
            "clause": "Clause",
            "standard": "Standard",
            # 设备依赖子图
            "equipment": "Equipment",
            "dependent_equipment": "Equipment",
            "zone": "Zone",
        }

        docs: list[Document] = []
        seen_keys: set[str] = set()  # 去重：同一 record 内相同 label+name 只保留一次

        for record in records:
            seen_keys.clear()
            for var_name, node_props in record.items():
                # 跳过 None（OPTIONAL MATCH 未匹配的节点）
                if node_props is None:
                    continue

                # 确定节点标签
                node_label = _LABEL_MAP.get(var_name, var_name)

                # 提取节点名称（用于去重和 metadata）
                node_name = node_props.get("name", "")

                # 同一 record 内去重（如 equipment 和 dependent_equipment 可能同名）
                dedup_key = f"{node_label}::{node_name}"
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                # 格式化 page_content：将属性转为 "键: 值" 文本
                content_lines = [
                    f"{k}: {v}" for k, v in node_props.items() if v is not None
                ]
                page_content = "\n".join(content_lines)

                # 构建 metadata
                metadata: dict = {
                    "node_label": node_label,
                    "node_name": node_name,
                    "hop_count": hop_count,
                    "search_type": "graph",
                }

                # 将节点原始属性也存入 metadata，供后续使用
                for k, v in node_props.items():
                    if v is not None:
                        metadata[f"graph_{k}"] = v

                docs.append(Document(
                    page_content=page_content,
                    metadata=metadata,
                ))

        logger.info(
            f"图记录转换完成：{len(records)} 条记录 → {len(docs)} 份 Document"
        )
        return docs

    # ────────────────────── 1. 去重 ──────────────────────

    @staticmethod
    def deduplicate(docs: list[Document]) -> list[Document]:
        """实体去重

        合并向量片段与图路径中内容重复的文档，保留信息最丰富的版本。
        去重策略：
            - 主键：metadata["id"]（PG 主键），若存在则直接按 id 去重
            - 兜底键：page_content 前 200 字符的 MD5 哈希
            - 重复文档合并：保留 metadata 更丰富的版本（字段更多），
              并将重复来源标记记入 metadata["dedup_sources"]

        Args:
            docs: 待去重的文档列表（可能来自向量检索 + 图遍历等多路来源）

        Returns:
            list[Document]: 去重后的文档列表
        """
        if not docs:
            return []

        seen: dict[str, Document] = {}  # dedup_key -> best_doc
        dedup_sources: dict[str, list[str]] = {}  # dedup_key -> [source_name, ...]

        for doc in docs:
            # 构建去重键
            pg_id = doc.metadata.get("id")
            if pg_id is not None:
                dedup_key = f"id::{pg_id}"
            else:
                content_hash = hashlib.md5(
                    doc.page_content[:200].encode("utf-8")
                ).hexdigest()
                dedup_key = f"hash::{content_hash}"

            source_name = doc.metadata.get("search_type", "unknown")

            if dedup_key not in seen:
                seen[dedup_key] = doc
                dedup_sources[dedup_key] = [source_name]
            else:
                # 重复文档：保留 metadata 更丰富的版本
                existing = seen[dedup_key]
                if len(doc.metadata) > len(existing.metadata):
                    seen[dedup_key] = doc
                dedup_sources[dedup_key].append(source_name)
                logger.debug(
                    f"去重：文档 [{dedup_key}] 在 {source_name} 中重复，已合并"
                )

        # 将去重来源信息写入保留文档的 metadata
        result: list[Document] = []
        for dedup_key, doc in seen.items():
            sources = dedup_sources[dedup_key]
            if len(sources) > 1:
                new_metadata = dict(doc.metadata)
                new_metadata["dedup_sources"] = sources
                result.append(Document(
                    page_content=doc.page_content,
                    metadata=new_metadata,
                ))
            else:
                result.append(doc)

        removed = len(docs) - len(result)
        if removed > 0:
            logger.info(f"去重完成：{len(docs)} → {len(result)}，移除 {removed} 份重复文档")
        return result

    # ────────────────────── 2. 排序 ──────────────────────

    @staticmethod
    def sort_by_relevance(docs: list[Document]) -> list[Document]:
        """相关性排序

        按综合相关度降序排列文档，确保最相关的内容排在前面。
        排序依据（优先级从高到低）：
            1. rrf_score（RRF 融合分数，hybrid 检索产生）
            2. score（单路检索的相似度分数：dense 余弦相似度 / BM25 分数）
            3. hop_weight（图遍历跳数权重，跳数越少权重越高）
            4. 无分数的文档排在最后，保持原始顺序

        图遍历跳数权重计算：hop_weight = 1.0 / (hop_count + 1)
            - 1 跳：0.5，2 跳：0.33，3 跳：0.25

        Args:
            docs: 待排序的文档列表

        Returns:
            list[Document]: 按相关度降序排列的文档列表
        """
        if not docs:
            return []

        def _extract_score(doc: Document) -> float:
            """提取文档的综合相关度分数"""
            # 优先使用 RRF 融合分数
            rrf_score = doc.metadata.get("rrf_score")
            if rrf_score is not None:
                return float(rrf_score)

            # 其次使用单路检索分数
            score = doc.metadata.get("score")
            if score is not None:
                return float(score)

            # 图遍历：按跳数计算权重（跳数越少越相关）
            hop_count = doc.metadata.get("hop_count")
            if hop_count is not None:
                return 1.0 / (int(hop_count) + 1)

            # 无分数信息，返回 0 排在最后
            return 0.0

        sorted_docs = sorted(docs, key=_extract_score, reverse=True)
        logger.info(
            f"相关性排序完成：{len(sorted_docs)} 份文档，"
            f"最高分={_extract_score(sorted_docs[0]):.4f}" if sorted_docs else "相关性排序完成：无文档"
        )
        return sorted_docs

    # ────────────────────── 3. 父文档回填 ──────────────────────

    @staticmethod
    def attach_parent_documents(
        chunks: list[Document],
        parent_map: dict[str, list[Document]],
        top_n: int = 3,
    ) -> list[Document]:
        """附加父文档内容

        将检索命中的子文档回填同一 source_file 下的完整父文档内容,
        提供更丰富的上下文信息。

        Args:
            chunks: 检索命中的子文档
            parent_map: source_file -> 同源子文档列表（由 db_retriever._build_parent_map() 构建）
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
            source_file = chunk.metadata.get("source_file", "")
            if not source_file or source_file not in parent_map:
                continue

            # 获取同源的所有子文档，拼接为完整父文档内容
            sibling_docs = parent_map[source_file]
            parent_content = "\n".join(doc.page_content for doc in sibling_docs)

            # 构建父文档，附加到结果末尾
            parent_doc = Document(
                page_content=parent_content,
                metadata={
                    "source_file": source_file,
                    "source_name": chunk.metadata.get("source_name", ""),
                    "category": chunk.metadata.get("category", ""),
                    "title": chunk.metadata.get("title", ""),
                    "parent_doc": True,
                    "child_count": len(sibling_docs),
                },
            )
            result.append(parent_doc)
            logger.info(
                f"父文档回填：source_file={source_file}，子文档数={len(sibling_docs)}"
            )

        return result

    # ────────────────────── 4. Token 截断 ──────────────────────

    @staticmethod
    def _estimate_tokens(text: str) -> int:
        """粗略估算 Token 数

        中文约 1.5 字/token，英文约 4 字符/token。
        采用简单启发式：中文按 1.5 字/token，其余按 4 字符/token。
        """
        chinese_chars = sum(1 for ch in text if '一' <= ch <= '鿿')
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

    # ────────────────────── 5. 异步融合管线 ──────────────────────

    async def fuse(
        self,
        vector_docs: list[Document],
        graph_records: list[dict] | None,
        token_budget: int = 0,
        parent_top_n: int = 3,
        graph_hop_count: int = 1,
    ) -> list[Document]:
        """异步融合管线 — 串联图记录转换 → 去重 → 排序 → 父文档回填 → Token截断

        将向量检索和图遍历的多路结果融合为统一的上下文，
        按转换、去重、排序、回填、截断的顺序依次处理，全程异步执行。

        parent_map 通过构造函数注入或 set_parent_map() 更新，
        调用方无需手动传入。

        Args:
            vector_docs: 向量检索结果（dense / sparse / hybrid）
            graph_records: 图遍历原始记录（Neo4j session.run().data() 的返回值），
                自动通过 graph_records_to_documents() 转为 Document
            token_budget: Token 预算上限，0 表示不截断
            parent_top_n: 父文档回填只取排名前 N 的文档
            graph_hop_count: 图遍历跳数，默认 1，影响排序权重

        Returns:
            list[Document]: 融合后的最终文档列表
        """
        # Step 0: 图记录 → Document（CPU 密集，放入线程池）
        graph_docs = await asyncio.to_thread(
            self.graph_records_to_documents, graph_records, graph_hop_count
        )

        # 合并多路文档
        all_docs = vector_docs + graph_docs
        logger.info(
            f"融合管线启动：向量文档={len(vector_docs)}，"
            f"图遍历文档={len(graph_docs)}，合计={len(all_docs)}"
        )

        if not all_docs:
            logger.warning("融合管线：输入文档为空，直接返回")
            return []

        # Step 1: 去重（CPU 密集，放入线程池避免阻塞事件循环）
        docs = await asyncio.to_thread(self.deduplicate, all_docs)

        # Step 2: 相关性排序（CPU 密集，放入线程池）
        docs = await asyncio.to_thread(self.sort_by_relevance, docs)

        # Step 3: 父文档回填（CPU 密集，放入线程池，使用注入的 parent_map）
        docs = await asyncio.to_thread(
            self.attach_parent_documents, docs, self._parent_map, parent_top_n
        )

        # Step 4: Token 预算截断（CPU 密集，放入线程池）
        if token_budget > 0:
            docs = await asyncio.to_thread(
                self.truncate_to_budget, docs, token_budget
            )

        logger.info(f"融合管线完成：最终文档数={len(docs)}")
        return docs
