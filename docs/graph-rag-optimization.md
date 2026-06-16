# GraphRAG 架构优化方案 — 基于 C9 项目实战经验

> 最后更新：2026-06-16
> 目标：为 DeepAgentsDemo2 的 graph_rag/ 模块补充实现细节，填入消防领域逻辑

---

## 一、当前状态

| 模块 | 当前状态 | 问题 |
|------|---------|------|
| `orchestrator.py` | 15 行 docstring | 无代码 |
| `entity_extractor.py` | 15 行 docstring | 无代码 |
| `vector_retriever.py` | 15 行 docstring | 无代码 |
| `graph_traverser.py` | 14 行 docstring | 无代码 |
| `context_fusion.py` | 14 行 docstring | 无代码 |
| `evaluator.py` | 15 行 docstring | 无代码 |
| `config.py` | 12 行 docstring | 无代码 |
| `graph_db/*` | 全部 docstring | 无代码 |
| `vector_db/*` | 全部 docstring | 无代码 |
| `ingestion/*` | 全部 docstring | 无代码 |
| `knowledge_tools.py` | **Mock 数据** | 简单关键词匹配，非真实检索 |

**结论**：架构文档（graph-rag-architecture.md）写得很完善，但代码为 0。本方案基于 C9 的实战经验，补充每个模块的实现细节。

---

## 二、C9 的实战经验（可直接借鉴）

### 2.1 三路检索 + RRF 融合（C9 hybrid_retrieval.py）

C9 的核心检索流程：
```
BM25（jieba 分词 + 中文停用词） + 向量检索（Milvus HNSW） + 图键值索引
         ↓
RRF (Reciprocal Rank Fusion, k=60) 融合排序
         ↓
去重（按 node_id，同一实体只保留最佳排名的 chunk）
```

**消防场景适配**：
- BM25 → 适合法规条款号、设备型号等精确关键词查询（如"GB 50974-2014"、"EPS电源-01"）
- 向量检索 → 适合语义模糊查询（如"ICU病房消防要注意什么"）
- 图键值索引 → **不需要**（C9 的 KV 索引只是精确匹配，不如直接查 Neo4j）
- 替换为：**图遍历** → 适合关联推理（如"EPS电源-01故障影响了谁"）

**消防场景的三路检索**：
```
BM25（精确关键词） + 向量检索（语义匹配） + 图遍历（关联推理）
         ↓
RRF 融合 + token 预算截断
```

### 2.2 中文 BM25 实现（C9 hybrid_retrieval.py）

C9 的 BM25 实现细节可以直接搬：
- jieba 分词 + 手挑中文停用词表（28 个，覆盖助词/连词/疑问词等）
- `rank_bm25.BM25Okapi` 库
- 分数 ≤ 0 的结果过滤掉

**消防场景适配**：
- 停用词表加消防领域高频虚词（"消防"、"安全"等区分度低的词考虑加入停用词）
- 分词后的词需要保留专业术语的完整性（如"烟感探测器"不应被切成"烟感"+"探测器"——加消防领域自定义词典）

### 2.3 Milvus 向量检索（C9 milvus_index_construction.py）

C9 的实现：
- HNSW 索引：M=16, efConstruction=200, COSINE 度量
- 搜索参数：ef=64
- BGE-small-zh-v1.5（512 维）→ 消防场景改用 DashScope text-embedding-v4（1024 维）
- 批量插入 batch_size=100
- 元数据过滤（category, difficulty 等字段）

**消防场景适配**：
- 维度：512 → 1024
- Embedding 模型：HuggingFace BGE → DashScope API
- Collection：1 个 → 3 个（fire_doc, fire_context, fire_image）
- 加稀疏向量字段（BM25 sparse vector），支持 Milvus 原生混合检索
- **修 C9 的 bug**：`sleep(2)` → 改用 Milvus API 轮询索引构建状态

### 2.4 Neo4j 图数据加载（C9 graph_data_preparation.py）

C9 从 Neo4j 加载数据 → 构建文档 → 分块 → 入 Milvus。

**关键教训**：
- C9 有 N+1 查询问题（每道菜单独查食材和步骤，200 道菜 = 400+ 次 Cypher）→ 消防场景必须用**单条聚合 Cypher**
- C9 的分块有 overlap 计算错误 → 消防场景直接用 LangChain 的 `RecursiveCharacterTextSplitter`
- C9 硬编码 `nodeId >= '200000000'` 过滤 → 消防场景不做这种硬编码

### 2.5 父文档回填（C9 hybrid_retrieval.py）

C9 实现了"父文档回填"：检索命中的是 chunk，但返回时替换为完整父文档（截断到最大字符数）。

**消防场景适配**：
- 法规文档特别需要：一个条款可能被切成多个 chunk，只看一个 chunk 不完整
- 配置化：`enable_parent_doc_retrieval: bool`, `parent_doc_top_n: int`, `parent_doc_max_chars: int`

### 2.6 生成模块（C9 generation_integration.py）

C9 的实现比较简单：拼接上下文 → 发给 LLM → 返回回答。

**C9 的缺陷（消防场景必须修）**：
- 无上下文长度管理 → 消防法规文档很长，必须加 **token 预算截断**
- 无来源引用 → 消防场景必须可溯源（"根据 GB 50974-2014 第 3.0.2 条[1]"）
- 无流式重试 → C9 有但实现不够健壮

---

## 三、C9 的教训（消防场景要避免的坑）

| C9 的问题 | 说明 | 消防场景的做法 |
|-----------|------|---------------|
| **每次查询 3-4 次 LLM 调用** | 关键词抽取调 LLM、路由调 LLM、图查询理解调 LLM、生成调 LLM | 简单查询只用 jieba 分词（0 次 LLM），复杂查询才用 LLM structured_output |
| **LLM 路由** | 每次查询都调 LLM 判断走哪条检索路径 | 规则路由（见 4.3 节），不浪费 LLM 调用 |
| **图推理是假的** | 700 行代码，推理链返回 placeholder 字符串 | 只做真正有用的图遍历（1-2 跳 Cypher），不做"图结构推理" |
| **内存 KV 索引** | 精确匹配，不如直接查 Neo4j | 不做内存 KV 索引，直接用 Neo4j 参数化 Cypher |
| **多个独立 Neo4j 连接** | 4 个模块各创建 driver | 共享连接管理器（单例 driver + 连接池） |
| **Cypher f-string 注入** | 用 f-string 拼接 Cypher 查询 | 全部用 `$param` 参数化查询 |
| **无评估** | 没有 RAGAS 或任何质量度量 | 必须加 RAGAS（架构文档已规划） |

---

## 四、优化后的架构

### 4.1 整体管线（5 步编排）

```
用户查询
  │
  Step 1: 实体抽取
  │    ├── 简单查询 → jieba 分词 + 停用词过滤（0 次 LLM 调用）
  │    └── 复杂查询 → LLM + with_structured_output（1 次 LLM 调用）
  │    输出：FireQueryEntities(equipment, zones, regulations, modules, constraints)
  │
  Step 2: 策略选择 + 并行检索
  │    ├── 规则路由（不调 LLM）：
  │    │    ├── 只提到设备名 → 图遍历（故障影响链）
  │    │    ├── 只提到区域名 → 图遍历（法规关联）+ 向量检索
  │    │    ├── 只提到法规名 → 向量检索
  │    │    └── 通用问题 → hybrid（向量 + BM25 + 图遍历）
  │    │
  │    └── 并行执行（ThreadPoolExecutor）：
  │         ├── BM25 检索（jieba 分词，精确关键词匹配）
  │         ├── 向量检索（Milvus hybrid: dense + sparse）
  │         └── 图遍历（Neo4j 参数化 Cypher，1-2 跳）
  │
  Step 3: 上下文融合
  │    ├── 按 entity_id 去重（向量片段和图路径可能命中同一实体）
  │    ├── RRF 排序（k=60，保留 C9 的实现）
  │    ├── 父文档回填（法规文档特别需要，可选开启）
  │    └── Token 预算截断（如 6000 tokens，为 prompt 和生成留空间）
  │    输出：融合后的有序上下文列表，附带来源元数据
  │
  Step 4: LLM 生成
  │    ├── 构建带来源编号的上下文 prompt
  │    ├── 调用 LLM 生成结构化回答
  │    └── 要求回答中标注来源引用（如"根据 GB 50974-2014[2]"）
  │
  Step 5: RAGAS 评估（可选，按配置开关）
       ├── ContextRelevance ≥ 0.7 → 通过
       └── < 0.7 → 兜底提示"知识库暂未收录该内容的完整答案"
```

**对比现有架构文档的 5 步管线**：结构一致，但补充了 C9 的实战细节：
- Step 1 加了 jieba 快速路径（简单查询不浪费 LLM）
- Step 2 加了 BM25 检索路径 + 并行执行 + 规则路由
- Step 3 加了父文档回填 + token 预算截断
- Step 4 加了来源引用要求

### 4.2 实体抽取设计

```python
# Pydantic 模型
class FireQueryEntities(BaseModel):
    """消防领域查询实体"""
    equipment: list[str] = Field(default_factory=list, description="消防设备名，如：烟感探测器-01、EPS电源")
    zones: list[str] = Field(default_factory=list, description="建筑区域，如：ICU病房、B栋3层")
    regulations: list[str] = Field(default_factory=list, description="法规/标准名，如：GB 50974-2014")
    modules: list[str] = Field(default_factory=list, description="系统模块，如：巡检管理、报警系统")
    constraints: dict[str, str] = Field(default_factory=dict, description="约束条件，如：{'风险等级': '一类重点'}")

# 快速路径：jieba 分词（0 次 LLM 调用）
def quick_extract(query: str) -> FireQueryEntities:
    """用 jieba 分词 + 消防领域词典 + 停用词过滤提取实体"""
    # 消防领域自定义词典：烟感探测器、喷淋泵、EPS电源 等
    # 匹配已知实体名（从 Neo4j 预加载的实体列表中匹配）
    ...

# 完整路径：LLM structured_output（1 次 LLM 调用）
def llm_extract(query: str, model: BaseChatModel) -> FireQueryEntities:
    """用 LLM 结构化输出提取复杂实体"""
    structured_model = model.with_structured_output(FireQueryEntities)
    result = structured_model.invoke(query)
    return result

# 路由逻辑
def extract_entities(query: str, model: BaseChatModel = None) -> FireQueryEntities:
    quick = quick_extract(query)
    if quick.has_any_entity():  # 简单查询 jieba 就够了
        return quick
    if model:  # 复杂查询用 LLM
        return llm_extract(query, model)
    return quick  # 兜底
```

### 4.3 规则策略选择（替代 LLM 路由）

```python
def select_strategy(entities: FireQueryEntities) -> str:
    """
    规则路由 — 不调 LLM，基于实体类型判断检索策略。
    返回: "vector" | "graph" | "hybrid"
    """
    # 只提到设备 → 图遍历（故障影响链场景）
    if entities.equipment and not entities.zones and not entities.regulations:
        return "graph"

    # 只提到法规/标准 → 向量检索（法规正文在 Milvus）
    if entities.regulations and not entities.equipment and not entities.zones:
        return "vector"

    # 提到区域 → hybrid（区域→法规关联用图，法规正文用向量）
    # 多种实体 → hybrid
    return "hybrid"
```

**对比 C9**：C9 每次查询都调 LLM 做路由分析，浪费 1 次 LLM 调用 + 1-2 秒延迟。消防场景用规则路由即可，因为实体类型和检索策略的对应关系是确定的。

### 4.4 图遍历设计（替代 C9 的多跳推理引擎）

C9 的 `graph_rag_retrieval.py` 有 700 行代码，支持多跳遍历、子图提取、路径查找、聚类分析——但推理部分全是 stub。消防场景**真正需要的**只有 3 种图查询：

```python
# graph_db/queries.py — 参数化 Cypher 查询模板

# 场景1：设备依赖追踪（故障影响链）
EQUIPMENT_DEPENDENCY = """
MATCH (e:Equipment {name: $equipment_name})-[:依赖*1..$max_depth]->(dep:Equipment)-[:安装于]->(z:Zone)
OPTIONAL MATCH (dep)-[:属于分类]->(et:EquipmentType)
RETURN e.name AS source, dep.name AS dependent, type(r) AS relation,
       z.name AS zone, et.name AS equipment_type
ORDER BY dep.name
"""

# 场景2：法规关联检索（区域→法规→条款→标准）
ZONE_REGULATION_CHAIN = """
MATCH (z:Zone)-[:属于分类]->(zt:ZoneType)-[:适用法规]->(reg:Regulation)-[:包含条款]->(c:Clause)
WHERE z.name CONTAINS $zone_name
OPTIONAL MATCH (c)-[:引用]->(s:Standard)
OPTIONAL MATCH (c)-[:要求配置]->(et:EquipmentType)
RETURN z.name AS zone, reg.name AS regulation, c.number AS clause,
       c.content AS content, s.name AS standard, et.name AS requirement
ORDER BY reg.name, c.number
"""

# 场景3：系统操作导航（模块→功能→步骤→前置条件）
MODULE_OPERATION_NAV = """
MATCH (m:Module)-[:包含功能]->(f:Function)-[:操作步骤]->(s:Step)
WHERE m.name CONTAINS $module_name
OPTIONAL MATCH (f)-[:前置条件]->(req:Requirement)
RETURN m.name AS module, f.name AS function, s.order AS step_order,
       s.description AS step_desc, req.description AS prerequisite
ORDER BY f.name, s.order
"""
```

**对比 C9**：
- C9 用 f-string 拼接 Cypher → 消防场景用 `$param` 参数化
- C9 的多跳遍历是通用可变深度 → 消防场景针对 3 种场景预写查询模板，更高效
- C9 的图推理是假的 → 消防场景不做图推理，只做确定的图遍历

### 4.5 上下文融合设计

```python
class ContextFusion:
    """上下文融合：去重 + RRF 排序 + 父文档回填 + Token 预算截断"""

    def fuse(
        self,
        query: str,
        bm25_results: list[Document],
        vector_results: list[Document],
        graph_results: list[Document],
        token_budget: int = 6000,
    ) -> list[Document]:
        # 1. 三路结果按来源标记
        labeled = [
            ("bm25", bm25_results),
            ("vector", vector_results),
            ("graph", graph_results),
        ]

        # 2. RRF 融合（复用 C9 的 _rrf_merge 实现）
        merged = self.rrf_merge(labeled, k=60)

        # 3. 父文档回填（法规文档特别需要）
        if self.config.enable_parent_doc_retrieval:
            merged = self.attach_parent_documents(merged)

        # 4. Token 预算截断
        merged = self.truncate_to_budget(merged, token_budget)

        return merged

    def rrf_merge(self, labeled_results, k=60):
        """C9 验证过的 RRF 融合实现，可直接搬"""
        # 按 entity_id 去重，同一实体只保留最佳排名
        # RRF score = sum(1 / (k + rank_i)) for each source
        ...

    def truncate_to_budget(self, docs: list[Document], budget: int) -> list[Document]:
        """Token 预算截断 — C9 没有这个，消防场景必须加"""
        total = 0
        result = []
        for doc in docs:  # 已按 RRF 分排序
            tokens = len(self.tokenizer.encode(doc.page_content))
            if total + tokens <= budget:
                result.append(doc)
                total += tokens
            else:
                remaining = budget - total
                if remaining > 100:  # 至少保留 100 token
                    truncated = self.tokenizer.decode(
                        self.tokenizer.encode(doc.page_content)[:remaining]
                    )
                    result.append(Document(page_content=truncated + "...", metadata=doc.metadata))
                break
        return result
```

### 4.6 Neo4j 连接管理

```python
# graph_db/connection.py
class Neo4jConnectionManager:
    """共享 Neo4j 连接管理器 — 单例模式，所有模块复用"""
    _instance = None
    _driver = None

    def __init__(self, uri: str, user: str, password: str, max_pool_size: int = 50):
        self._driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            max_connection_pool_size=max_pool_size,
            connection_acquisition_timeout=30,
        )

    @classmethod
    def get_instance(cls, config) -> 'Neo4jConnectionManager':
        if cls._instance is None:
            cls._instance = cls(config.neo4j_uri, config.neo4j_user, config.neo4j_password)
        return cls._instance

    def get_session(self):
        return self._driver.session()

    def health_check(self) -> bool:
        try:
            with self._driver.session() as s:
                s.run("RETURN 1")
            return True
        except Exception:
            return False

    def close(self):
        if self._driver:
            self._driver.close()
            Neo4jConnectionManager._instance = None
```

**对比 C9**：C9 有 4 个独立 Neo4j driver，消防场景只用 1 个共享 driver。

### 4.7 配置模块

```python
# config.py
class GraphRAGConfig(BaseModel):
    """GraphRAG 配置 — 所有敏感值从 .env 读取"""
    # Neo4j
    neo4j_uri: str = Field(default_factory=lambda: os.getenv("NEO4J_URI", "bolt://localhost:7687"))
    neo4j_user: str = Field(default_factory=lambda: os.getenv("NEO4J_USER", "neo4j"))
    neo4j_password: str = Field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", ""))

    # Milvus
    milvus_host: str = Field(default_factory=lambda: os.getenv("MILVUS_HOST", "localhost"))
    milvus_port: int = 19530

    # DashScope Embedding
    dashscope_api_key: str = Field(default_factory=lambda: os.getenv("DASHSCOPE_API_KEY", ""))
    embedding_model: str = "text-embedding-v4"
    embedding_dim: int = 1024

    # 检索参数
    default_top_k: int = 5
    default_graph_depth: int = 2
    rrf_k: int = 60
    token_budget: int = 6000

    # 父文档回填
    enable_parent_doc_retrieval: bool = True
    parent_doc_top_n: int = 3
    parent_doc_max_chars: int = 8000

    # RAGAS 评估
    enable_evaluation: bool = False  # 默认关闭，按需开启
    ragas_threshold: float = 0.7

    @model_validator(mode='after')
    def validate_config(self):
        if not self.neo4j_password:
            raise ValueError("NEO4J_PASSWORD 必须在 .env 中设置")
        if not self.dashscope_api_key:
            raise ValueError("DASHSCOPE_API_KEY 必须在 .env 中设置")
        return self
```

### 4.8 编排器（核心入口）

```python
# orchestrator.py
class GraphRAGOrchestrator:
    """GraphRAG 查询编排器 — 5 步管线"""

    def __init__(self, config: GraphRAGConfig):
        self.config = config
        self.entity_extractor = EntityExtractor(config)
        self.vector_retriever = VectorRetriever(config)
        self.graph_traverser = GraphTraverser(config)
        self.bm25_search = BM25Search()       # 内存 BM25，初始化时建索引
        self.context_fusion = ContextFusion(config)
        self.evaluator = RAGEvaluator(config)  # 可选

    def orchestrate(self, query: str, **kwargs) -> GraphRAGResult:
        # Step 1: 实体抽取
        entities = self.entity_extractor.extract(query)

        # Step 2: 策略选择 + 并行检索
        strategy = select_strategy(entities)

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {}

            if strategy in ("vector", "hybrid"):
                futures["vector"] = pool.submit(
                    self.vector_retriever.search, query, entities, kwargs.get("top_k", 5)
                )

            if strategy in ("graph", "hybrid"):
                futures["graph"] = pool.submit(
                    self.graph_traverser.traverse, entities, kwargs.get("graph_depth", 2)
                )

            if strategy == "hybrid":
                futures["bm25"] = pool.submit(
                    self.bm25_search.search, query, kwargs.get("top_k", 5)
                )

            results = {k: f.result() for k, f in futures.items()}

        # Step 3: 上下文融合
        fused = self.context_fusion.fuse(
            query,
            bm25_results=results.get("bm25", []),
            vector_results=results.get("vector", []),
            graph_results=results.get("graph", []),
            token_budget=self.config.token_budget,
        )

        # Step 4: LLM 生成
        answer = self.generate_with_citations(query, fused)

        # Step 5: RAGAS 评估（可选）
        score = None
        if self.config.enable_evaluation:
            score = self.evaluator.evaluate(query, fused, answer)

        return GraphRAGResult(
            answer=answer,
            sources=[...],
            strategy=strategy,
            score=score,
        )
```

### 4.9 knowledge_tools.py 改造

```python
# 改造前：Mock 关键词匹配
# 改造后：调用真实编排器

@mcp.tool(name="graph_rag_search")
async def graph_rag_search(query: str, ...) -> dict:
    # 真实编排器调用
    result = orchestrator.orchestrate(query, top_k=max_vector_results, graph_depth=graph_depth)
    return {
        "answer": result.answer,
        "sources": result.sources,
        "score": result.score,
        "status": "success" if (result.score or 1.0) >= score_threshold else "low_score",
    }

@mcp.tool(name="knowledge_search")
async def knowledge_search(query: str, ...) -> dict:
    # 纯向量检索，不走编排器
    results = vector_retriever.search(query, top_k=max_results)
    return {"total": len(results), "items": results}

@mcp.tool(name="graph_query")
async def graph_query(entity: str, ...) -> dict:
    # 纯图遍历，不走编排器
    results = graph_traverser.traverse(entity, depth=depth, relation_types=relation_types)
    return {"paths": results.paths, "entities": results.entities, "total_paths": len(results.paths)}
```

---

## 五、各模块实施要点

### 5.1 graph_db/connection.py

| 项目 | 要点 |
|------|------|
| 模式 | 单例，全局共享一个 driver |
| 连接池 | `max_connection_pool_size=50` |
| 超时 | `connection_acquisition_timeout=30s` |
| 健康检查 | `session.run("RETURN 1")` |
| 生命周期 | 跟随 MCP Server 的 lifespan |

### 5.2 graph_db/queries.py

| 查询模板 | 起点 | 遍历路径 | 用途 |
|----------|------|----------|------|
| `EQUIPMENT_DEPENDENCY` | 设备名 | Equipment → Equipment(依赖) → Zone | 故障影响链 |
| `ZONE_REGULATION_CHAIN` | 区域名 | Zone → ZoneType → Regulation → Clause → Standard | 法规关联 |
| `MODULE_OPERATION_NAV` | 模块名 | Module → Function → Step → Requirement | 操作导航 |

**原则**：
- 全部用 `$param` 参数化，禁止 f-string
- 用 `OPTIONAL MATCH` 避免缺少关系时丢失主节点
- 限定最大深度 1-2 跳，不做无限深度遍历

### 5.3 graph_db/schema.py

把 docstring 中的 11 种节点 + 11 种关系定义为 Python 常量：

```python
# 节点标签
class NodeLabel:
    MODULE = "Module"
    FUNCTION = "Function"
    STEP = "Step"
    REQUIREMENT = "Requirement"
    REGULATION = "Regulation"
    CLAUSE = "Clause"
    STANDARD = "Standard"
    ZONE_TYPE = "ZoneType"
    EQUIPMENT_TYPE = "EquipmentType"
    EQUIPMENT = "Equipment"
    ZONE = "Zone"

# 关系类型
class RelType:
    CONTAINS_FUNCTION = "包含功能"
    HAS_STEP = "操作步骤"
    NEXT_STEP = "下一步"
    PREREQUISITE = "前置条件"
    CONTAINS_CLAUSE = "包含条款"
    REFERENCES = "引用"
    APPLICABLE_REGULATION = "适用法规"
    REQUIRES_CONFIG = "要求配置"
    BELONGS_TO_CATEGORY = "属于分类"
    INSTALLED_IN = "安装于"
    DEPENDS_ON = "依赖"
```

### 5.4 vector_db/collections.py

3 个 Collection 的 Schema 定义：

| Collection | 向量类型 | 维度 | 主要字段 |
|------------|---------|------|----------|
| `fire_doc_collection` | dense + sparse | 1024 | id, text, category, source_file, title |
| `fire_context_collection` | dense | 1024 | id, text, session_id, timestamp |
| `fire_image_collection` | dense (多模态) | 1024 | id, text, image_path, source_file, title |

**对比 C9**：C9 只有 1 个 Collection，消防场景需要 3 个。C9 用 HNSW（M=16, efConstruction=200），消防场景同样用 HNSW 但维度 1024。

### 5.5 vector_db/db_retriever.py

3 种检索策略：

| 策略 | 适用场景 | 实现 |
|------|---------|------|
| `dense` | 语义模糊查询 | embedding + COSINE similarity |
| `sparse` | 精确关键词 | BM25 sparse vector |
| `hybrid` | 通用（推荐默认） | dense + sparse 加权融合 |

**对比 C9**：C9 只做了 dense 检索 + 外部 BM25Okapi，消防场景可以直接用 Milvus 原生的 sparse vector 支持，不需要额外维护 BM25 索引——但 C9 的外部 BM25 方案也可以保留作为备选，因为 jieba 分词对中文效果更好。

### 5.6 ingestion/ 数据写入管线

```
知识文档（法规PDF / 操作手册Word / 设备照片 / 巡检报告MD）
  │
  ▼
dispatcher.py — 格式识别与引擎路由
  │
  ├── .pdf  → pdf_parser (DotsOCR + VLLM → Markdown + 图片)
  ├── .png/.jpg → image_parser (OCR + 多模态 LLM → 描述)
  ├── .docx/.html → office_parser (Unstructured → Markdown)
  └── .md → md_parser (直接读取)
  │
  ▼
统一输出: ParsedDocument(text, images, metadata)
  │
  ├─ text → splitter → embedding → Milvus fire_doc_collection
  ├─ images → 多模态描述 → embedding → Milvus fire_image_collection
  └─ text → entity_relation_extractor → Neo4j
```

**C9 没有这个管线**，C9 的数据是直接从 Neo4j 加载的。消防场景需要这个管线因为：
1. 法规文档是 PDF/Word 格式，需要解析
2. 设备照片需要 OCR
3. 法规文档中的实体和关系需要抽取写入 Neo4j

### 5.7 ingestion/splitter.py

C9 的分块方式：按 `## ` 标题切分 + 固定长度滑动窗口（有 overlap bug）。

消防场景应直接用 LangChain 的 `RecursiveCharacterTextSplitter`：
- 按标题层级切分（法规的章→节→条→款）
- 对过长段落自动二次切分
- overlap 计算正确
- 支持 token 计数（不只是字符计数）

### 5.8 ingestion/entity_relation_extractor.py

C9 没有这个模块（C9 的数据是 AI Agent 预处理好的）。

消防场景需要：
- 法规文档 → Regulation + Clause + Standard 节点 + 引用/包含条款 边
- 操作手册 → Module + Function + Step 节点 + 包含功能/操作步骤 边
- 用 LLM `with_structured_output` 抽取，配合规则辅助（条款号格式识别）

### 5.9 ingestion/biz_sync.py

C9 没有这个模块。

消防场景需要把 Java 后端的设备台账、建筑分区、设备依赖关系同步到 Neo4j。
- 增量同步：消息队列或定时任务
- 全量同步：初次部署时批量导入

---

## 六、实施顺序

### Phase 2（对应架构文档的 Phase 2 — GraphRAG 基础）

| 步骤 | 文件 | 内容 | 依赖 |
|------|------|------|------|
| 2.1 | `config.py` | 实现配置加载（.env + Pydantic 验证） | 无 |
| 2.2 | `graph_db/connection.py` | 实现 Neo4j 连接管理器 | 2.1 |
| 2.3 | `graph_db/schema.py` | 定义节点/关系常量 | 无 |
| 2.4 | `graph_db/queries.py` | 写 3 个参数化 Cypher 模板 | 2.3 |
| 2.5 | `vector_db/collections.py` | 定义 3 个 Collection Schema | 2.1 |
| 2.6 | `vector_db/db_operator.py` | 实现 Milvus 数据插入 | 2.5 |
| 2.7 | `vector_db/db_retriever.py` | 实现 dense/sparse/hybrid 检索 | 2.5 |
| 2.8 | `entity_extractor.py` | 实现实体抽取（jieba + LLM） | 2.1 |
| 2.9 | `graph_traverser.py` | 实现图遍历（调用 queries.py 模板） | 2.2, 2.4 |
| 2.10 | `vector_retriever.py` | 包装 db_retriever，对外统一接口 | 2.7 |

### Phase 3（对应架构文档的 Phase 3 — 融合 + 管理助手核心）

| 步骤 | 文件 | 内容 | 依赖 |
|------|------|------|------|
| 3.1 | `context_fusion.py` | 实现 RRF + 去重 + 父文档回填 + Token 截断 | 2.8-2.10 |
| 3.2 | `evaluator.py` | 实现 RAGAS 评估 | 2.1 |
| 3.3 | `orchestrator.py` | 实现 5 步编排管线 | 3.1, 3.2 |
| 3.4 | `knowledge_tools.py` | Mock → 真实编排器调用 | 3.3 |

### Phase 4（对应架构文档的 Phase 4 — 数据管线）

| 步骤 | 文件 | 内容 | 依赖 |
|------|------|------|------|
| 4.1 | `ingestion/doc_parser/*` | 多模态文档解析 | 2.1 |
| 4.2 | `ingestion/splitter.py` | Markdown 切分 | 4.1 |
| 4.3 | `ingestion/embedding.py` | DashScope Embedding | 2.5 |
| 4.4 | `ingestion/entity_relation_extractor.py` | 实体/关系抽取 | 2.2, 2.3 |
| 4.5 | `ingestion/biz_sync.py` | 业务数据同步 | 2.2 |

---

## 七、与现有架构文档的对照

现有 `graph-rag-architecture.md` 的设计已经很好，本方案**不改变架构**，而是**补充实现细节**：

| 架构文档描述 | 本方案补充 |
|-------------|-----------|
| "5步管线" | 补充了每步的具体实现方式（jieba快路径、RRF融合、token截断等） |
| "实体抽取" | 补充了 quick_extract + llm_extract 双路径 |
| "并行检索" | 补充了 ThreadPoolExecutor 并行 + 规则路由（不用LLM） |
| "上下文融合" | 补充了父文档回填（来自C9实战）+ token预算截断 |
| "RAGAS评估" | 补充了可选开关 + 阈值处理 |
| "参数化Cypher" | 补充了 3 个具体查询模板 |
| "graph_query工具" | 补充了改造方案（Mock → 真实） |

**来自 C9 的新增经验（原架构文档没有的）**：
1. BM25 外部索引（jieba 分词 + rank_bm25）——作为 Milvus sparse vector 的补充
2. 父文档回填 ——法规文档特别需要
3. RRF 融合的具体实现细节（去重策略、同源最佳排名、canonical document 选择）
4. 共享 Neo4j 连接管理器
5. jieba 快速实体提取路径（简单查询不调 LLM）
6. 中文停用词表
7. 消防领域自定义分词词典
