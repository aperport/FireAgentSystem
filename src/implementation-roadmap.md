# 消防后勤智能助手 — 实施路线图（基于当前代码现状）

> 生成日期：2026-06-22
> 原则：**先主流程跑通，优化方案在后**

---

## 一、当前代码现状总览

### 1.1 模块完成度

| 模块 | 完成度 | 状态说明 |
|------|--------|----------|
| **Agent 主流程** | 85% | `main_agent.py` 完整实现，子 Agent YAML 配置完整，中间件链完整，懒加载代理完整 |
| **MCP Server 框架** | 70% | `server_main.py` + `http_base.py` + 工具注册完整，但所有工具均为 Mock 数据 |
| **MCP 工具定义** | 90% | 11 个工具全部注册，Pydantic 数据模型（`mcp_tools_bean.py`）完整，Mock 返回结构正确 |
| **中间件** | 80% | 3 个中间件全部实现，消防领域已适配；`memory_update` 仍用手动 JSON 解析 |
| **GraphRAG 向量检索** | 90% | PGVectorManager + HybridRetrievalModule + VectorRetriever + ContextFusionModule 全部实现；去重/排序/父文档回填/Token截断完整 |
| **GraphRAG 图数据库** | 85% | Neo4jDriver + schema.py + queries.py + writer.py 已完成；graph_traverser.py 三级降级路由已实现 |
| **GraphRAG 编排层** | 75% | orchestrator.py 五步管线已实现（实体抽取→并行检索→去重融合→结果持久化），但存在硬编码连接参数和每次请求重建实例的问题 |
| **GraphRAG 实体抽取** | 95% | entity_extractor.py LLM+NER并行抽取 + 融合去重完整；rule_extractors.py 条款号正则补充完整 |
| **数据入库管线** | 70% | md_parser.py + splitter.py + embedding.py + db_operator.py + entity_relation_extractor.py + save_data.py 已实现；PDF/Office/图片解析仍为骨架 |
| **项目入口** | 0% | `run.py` 只有 docstring，无实际代码 |
| **测试** | 70% | Schema / MCP Tools / Middleware / SubAgent / E2E Phase1 测试已覆盖 |

### 1.2 关键偏离（与设计文档的差异）

| 设计文档 | 实际代码 | 影响 |
|----------|----------|------|
| 向量数据库用 **Milvus** | 实际用 **PostgreSQL + pgvector** | 无功能影响，PG 生态更轻量，运维简单 |
| Embedding 用 **DashScope text-embedding-v4（1024维）** | 实际用 **HuggingFace BAAI/bge-small-zh-v1.5（512维）** | DDL 中 vector(512) 与此一致；docstring 写 1024 需修正 |
| 向量表设计 3 个 Collection | 实际 DDL 只建了 **2 个**（`fire_doc_collection` + `fire_image_collection`） | 缺 `fire_context_collection`（对话历史），短期不需要 |
| 子 Agent 名称 `fire-qa-assistant` / `fire-management-analyst` | YAML 文件名正确，但 `main_agent.py` 中匹配的是 `"analyst"` | ⚠️ **Bug**：中间件注入永远匹配不上 |
| `knowledge_tools.py` Mock 数据 | Mock 关键词匹配实现，3 个工具全部可用 | 接入真实检索后替换即可 |
| `db_operator.py` 全局实例化 `PGVectorManager` | 硬编码 `"xxx"` 密码 + `logger = get_logger`（缺括号） | ⚠️ **Bug**：logger 调用报错；硬编码凭据 |

### 1.3 已发现的 Bug

---

## 二、主流程跑通路线图

> 目标：**用户提问 → 主 Agent 路由 → 子 Agent 委派 → MCP 工具调用 → 返回结果**
> 策略：MCP 工具先保持 Mock，GraphRAG 先用最简实现，逐步替换为真实后端

### Phase 0：修复阻塞性 Bug（1天）

| # | 任务 | 文件 | 改动 |
|---|------|------|------|
| 1 | 修复子 Agent 中间件注入匹配 | `main_agent.py` | `"analyst"` → 匹配 YAML 中的实际 name |
| 2 | 修复 `db_operator.py` logger bug | `db_operator.py` | `get_logger` → `get_logger(__name__)` |
| 3 | 修复 `db_operator.py` 硬编码凭据 | `db_operator.py` | 改为从 `graph_rag.config` 读取或延迟初始化 |
| 4 | 统一 DDL 中 vector 维度文档 | `collections.py` | docstring 与 DDL 保持一致（当前 512 维） |

**验收**：现有测试全部通过，`main_agent.py` 中间件注入可正确匹配到子 Agent。

---

### Phase 1：主流程端到端跑通（3-5天）

**目标**：从 CLI 或 API 发起对话，主 Agent 能正确路由到子 Agent，子 Agent 能调用 MCP 工具（Mock 数据）并返回结果。

#### 1.1 实现项目入口 `run.py`

```
当前状态：run.py 仅有 docstring
需要实现：
  - Agent 模式：命令行交互对话（循环读取输入 → invoke → 打印输出）
  - MCP Server 模式：启动 FastMCP 服务
  - 命令行参数解析（argparse / click）
```

#### 1.2 实现最小 API 视图层

```
当前状态：api_view/ 为空
最小实现（FastAPI）：
  - POST /chat          — 对话接口（同步/流式）
  - GET  /sessions      — 会话列表
  - DELETE /sessions/{id} — 删除会话
  - SSE  /stream/{id}   — 流式输出

关键依赖：
  - ChatRequest / ChatResponse / Stream*Event 等 Schema 已在 schema.py 中定义
  - Agent 实例通过 get_agent_async() 获取
  - thread_id 传递给 Agent 实现连续会话
```

#### 1.3 MCP Server 与 Agent 端联调

```
当前状态：
  - MCP Server 可独立启动（server_main.py）
  - MCP Client 可连接加载工具（MCP_client.py）
  - 但两者未在同一进程中联调过

需要验证：
  - MCP Server 启动 → Client 连接 → 工具加载 → 工具调用 → Mock 数据返回
  - 主 Agent → 子 Agent 委派 → 子 Agent 调用 MCP 工具 → 结果返回主 Agent
```

#### 1.4 关键配置确认

```
需要确认/调整的配置：
  - MCP_SERVER_URL：Client 连接 Server 的地址
  - JAVA_API_BASE_URL：Server 连接 Java 后端的地址（Mock 阶段不需要真实 Java）
  - MongoDB URI：Checkpoint 存储（如果没有 MongoDB 可临时用 MemorySaver）
  - OpenSandbox：API Key 和配置（如果沙箱不可用，主流程无需沙箱也能跑）
```

**验收标准**：
1. `python run.py --mode agent` 能启动对话
2. 输入"ICU病房消防系统要满足哪些要求" → 主 Agent 路由到问答助手 → 调用 `graph_rag_search` → 返回 Mock 答案
3. 输入"本月巡检完成率" → 主 Agent 路由到管理助手 → 调用 `fire_report_generate` → 返回 Mock 报表
4. 连续对话使用同一 thread_id，上下文保持

---

### Phase 2：GraphRAG 基础 — 向量检索真实化 ✅ 已完成

**目标**：`knowledge_search` 工具从 Mock 替换为真实的 PG 向量检索，问答助手能基于入库文档回答问题。

#### 2.1 ~~实现 graph_rag/config.py~~ ⚠️ 仍为骨架

```
当前状态：docstring 空文件
需要实现：
  - GraphRAGConfig 数据类，从 .env 读取所有配置
  - PG 连接参数、Neo4j 连接参数、Embedding 模型参数、检索参数
  - 配置验证（必填项检查）
```

#### 2.2 ~~修复并完善 db_operator.py~~ ✅ 已完成基础修复

```
当前状态：有基础实现但有 bug
需要修复：
  - logger 缺括号 bug（Phase 0 已修）
  - 硬编码 PG 凭据 → 从 config 读取
  - 延迟初始化 PGVectorManager（不再模块级实例化）
需要完善：
  - 批量插入（当前逐条 INSERT，改为 executemany 或 batch）
  - 重复数据检测（INSERT 前检查是否已存在）
```

#### 2.3 ~~实现最小数据入库管线~~ ✅ 已完成

```
当前状态：ingestion/ 全部为空
最小实现（只支持 Markdown）：
  - md_parser.py：直接读取 Markdown 文件，输出 ParsedDocument
  - splitter.py：用 LangChain RecursiveCharacterTextSplitter 切分
  - embedding.py：调用 PGVectorManager.embeddings 向量化
  - 串联：md_parser → splitter → embedding → db_operator.insert_chunks()

暂不实现：
  - pdf_parser / image_parser / office_parser（Phase 4）
  - entity_relation_extractor（Phase 3）
  - biz_sync（Phase 3）
```

#### 2.4 ~~替换 knowledge_search 为真实检索~~ ✅ 已完成

```
当前状态：Mock 关键词匹配
改造为：
  1. 初始化 PGVectorManager + HybridRetrievalModule
  2. knowledge_search → 调用 VectorRetriever.search(query, search_type="hybrid")
  3. 返回结构化的检索结果（保留现有的返回格式）

不改：
  - graph_rag_search 和 graph_query 暂时保持 Mock（Phase 3 替换）
```

#### 2.5 ~~准备测试知识库数据~~ ✅ 已完成

```
需要准备：
  - 3-5 个 Markdown 格式的消防知识文档
    - 消防法规摘要（如 GB 50974-2014 关键条款）
    - 系统操作手册（巡检管理操作规程等）
    - 设备知识（烟感探测器、喷淋系统等）
  - 通过入库管线写入 PG
  - 验证向量检索能召回相关内容
```

**验收标准**：
1. 能将 Markdown 文档入库到 PG
2. `knowledge_search("ICU病房消防要求")` 返回真实检索结果
3. 问答助手能基于入库文档给出有依据的回答

---

### Phase 3：GraphRAG 融合 — 图遍历 + 编排器 ✅ 已完成

**目标**：`graph_rag_search` 和 `graph_query` 从 Mock 替换为真实的向量+图融合检索。

#### 3.1 ~~实现 graph_db/queries.py~~ ✅ 已完成

```
当前状态：docstring 空文件
需要实现 3 个参数化 Cypher 查询模板：
  - EQUIPMENT_DEPENDENCY：设备依赖追踪（故障影响链）
  - ZONE_REGULATION_CHAIN：区域→法规→条款关联
  - MODULE_OPERATION_NAV：模块→功能→步骤导航
原则：全部用 $param 参数化，不做 f-string 拼接
```

#### 3.2 ~~实现 graph_traverser.py~~ ✅ 已完成

```
当前状态：docstring 空文件
需要实现：
  - GraphTraverser 类，接收 Neo4jDriver
  - traverse(entities, depth) → 执行 queries.py 中的 Cypher 模板
  - 结果转为 Document 列表（与向量检索结果统一格式）
  - 限定 1-2 跳，不做无限深度遍历
```

#### 3.3 ~~实现 entity_extractor.py~~ ✅ 已完成

```
当前状态：docstring 空文件
需要实现（两路径）：
  - quick_extract(query) → jieba 分词 + 消防领域词典匹配（0 次 LLM）
  - llm_extract(query, model) → with_structured_output 结构化输出（1 次 LLM）
  - 路由逻辑：简单查询用 jieba，复杂查询用 LLM
```

#### 3.4 ~~完善 context_fusion.py~~ ✅ 已完成

```
当前状态：父文档回填 + Token 截断已实现，缺实体去重和排序
需要补充：
  - entity_id 去重（向量片段和图路径可能命中同一实体）
  - RRF 融合（三路：BM25 + dense + graph）
  - 注：_rrf_merge 已在 db_retriever.py 中实现，可复用或提取为公共方法
```

#### 3.5 ~~实现 orchestrator.py~~ ✅ 已实现（需优化）

```
当前状态：docstring 空文件
需要实现：
  - GraphRAGOrchestrator 类
  - orchestrate(query) 五步管线：
    1. 实体抽取（entity_extractor）
    2. 策略选择 + 并行检索（规则路由，不调 LLM）
    3. 上下文融合（context_fusion）
    4. LLM 生成（带来源引用）
    5. 可选 RAGAS 评估
  - ThreadPoolExecutor 并行执行检索
```

#### 3.6 ~~替换 knowledge_tools.py 为真实调用~~ ✅ 已完成

```
改造：
  - graph_rag_search → 调用 orchestrator.orchestrate(query)
  - knowledge_search → 保持 Phase 2 的 VectorRetriever（已真实化）
  - graph_query → 调用 GraphTraverser.traverse()
```

#### 3.7 ~~Neo4j 初始数据写入~~ ✅ 已完成

```
手工或脚本写入测试数据：
  - 系统操作子图：Module → Function → Step → Requirement
  - 法规关联子图：ZoneType → Regulation → Clause → Standard
  - 设备依赖子图：Equipment → Equipment(依赖) → Zone

可通过以下方式之一：
  a. 写一个 init_neo4j.py 脚本，用 Neo4jDriver 执行 Cypher CREATE
  b. 使用 biz_sync.py（但需先实现）
  推荐 a，最快跑通
```

**验收标准**：
1. Neo4j 中有测试数据，Cypher 查询能返回结果
2. `graph_query("EPS电源-01")` 返回真实的设备依赖路径
3. `graph_rag_search("ICU病房消防系统要求")` 返回向量+图融合结果
4. 问答助手的 `graph_rag_search` 工具返回真实编排结果

---

### Phase 4：MCP 工具真实化 — Java 后端对接（待开始）

**目标**：6 个明细工具 + 2 个高层工具从 Mock 替换为真实 Java 后端 API 调用。

#### 4.1 Java 后端 API 联调

```
当前状态：所有 fire_*_tools.py 和 report_tools.py 均为 Mock + TODO
改造步骤：
  1. 确认 Java 后端 API 接口定义（URL、参数、返回格式）
  2. 在 http_base.py 的 lifespan 中初始化 httpx.AsyncClient
  3. 每个工具内部用 ctx.request_context.lifespan_context["http_client"] 获取 client
  4. 替换 Mock 返回为 httpx 调用结果

优先级：
  P0：fire_report_generate、fire_quality_evaluate（管理助手核心）
  P1：6 个明细查询工具
```

#### 4.2 数据入库管线扩展

```
当前状态：Phase 2 只实现了 md_parser
扩展：
  - pdf_parser.py：DotsOCR 或 PyMuPDF 解析
  - office_parser.py：Unstructured 解析
  - image_parser.py：OCR + 多模态描述
  - dispatcher.py：格式路由

暂不实现：
  - biz_sync.py（业务数据同步，需 Java 后端配合）
  - entity_relation_extractor.py（文档→图自动抽取，可手工录入替代）
```

**验收标准**：
1. 管理助手能调用 `fire_report_generate` 返回真实报表数据
2. 管理助手能调用 `fire_quality_evaluate` 返回真实评鉴结论
3. PDF/Word 文档能通过入库管线写入 PG 和 Neo4j

---

## 三、完整实施甘特图

```
Week 1
  ├── Phase 0: 修复 Bug（1天）
  └── Phase 1: 主流程跑通（3-5天）
       ├── run.py 入口实现
       ├── api_view 最小实现
       ├── MCP 联调验证
       └── 配置确认

Week 2-3
  └── Phase 2: GraphRAG 向量检索真实化（5-7天）
       ├── config.py 实现
       ├── db_operator.py 修复完善
       ├── 最小入库管线（md → split → embed → insert）
       ├── knowledge_search 真实化
       └── 测试知识库数据准备

Week 3-4
  └── Phase 3: GraphRAG 图遍历 + 编排器（5-7天）
       ├── queries.py 实现
       ├── graph_traverser.py 实现
       ├── entity_extractor.py 实现
       ├── context_fusion.py 补全
       ├── orchestrator.py 实现
       ├── knowledge_tools.py 真实化
       └── Neo4j 初始数据

Week 5-6
  └── Phase 4: MCP 工具真实化 + 数据管线扩展
       ├── Java 后端 API 对接
       ├── PDF/Office 文档解析
       └── 集成测试
```

---

## 四、各模块详细设计（基于当前代码）

### 4.1 Agent 主流程（已实现，需微调）

```
用户输入
  ↓
run.py / api_view
  ↓
get_agent_async() → create_main_agent()
  ↓
主 Agent（create_deep_agent）
  ├── system_prompt → 路由规则
  ├── 中间件链：
  │   1. ContextInjectionMiddleware（before_agent）— 注入 user_id
  │   2. SummarizationToolMiddleware（自动触发）— 上下文过长时摘要
  │   3. MemoryUpdateMiddleware（aafter_agent）— 自动更新偏好
  │   4. ModelCallLimitMiddleware — ≤50 次
  │   5. ToolCallLimitMiddleware — ≤200 次
  ├── 子 Agent 委派：
  │   ├── fire-qa-assistant → knowledge_search / graph_rag_search / graph_query
  │   └── fire-management-analyst → fire_report_generate / fire_quality_evaluate / 6个明细工具 / graph_query
  └── CompositeBackend 分流：
      ├── /memories/ → StoreBackend（用户偏好）
      └── 其他 → OpenSandbox
```

**需要修复**：`main_agent.py:155` 子 Agent 名称匹配逻辑。

### 4.2 GraphRAG 向量检索（已实现核心，需串联）

```
当前已实现：
  PGVectorManager      ← PG 连接 + 表创建 + Embedding 模型
  HybridRetrievalModule ← dense/bm25/hybrid 三种检索 + RRF 融合
  VectorRetriever      ← 统一入口 + 父文档回填 + Token 截断
  ContextFusionModule  ← 父文档回填 + Token 截断

待串联：
  knowledge_tools.py → VectorRetriever → HybridRetrievalModule → PGVectorManager

初始化流程：
  1. 读取 config → 创建 PGVectorManager
  2. 创建 HybridRetrievalModule（传入 PGVectorManager）
  3. 调用 rebuild_bm25_index() 初始化 BM25
  4. 创建 VectorRetriever（传入 HybridRetrievalModule）
  5. knowledge_search 调用 VectorRetriever.search()
```

### 4.3 GraphRAG 图遍历（仅连接层实现）

```
当前已实现：
  Neo4jDriver          ← 同步/异步连接 + 健康检查
  schema.py            ← 11 种节点 dataclass

待实现：
  queries.py           ← 3 种参数化 Cypher 模板
  graph_traverser.py   ← 执行查询 + 结果转 Document

初始化流程：
  1. 读取 config → 创建 Neo4jDriver
  2. graph_query → GraphTraverser → Neo4jDriver → queries.py
```

### 4.4 GraphRAG 编排器（全部待实现）

```
orchestrator.py 五步管线：

Step 1: entity_extractor.py
  ├── quick_extract(query)     → jieba 分词 + 词典匹配，0 次 LLM
  └── llm_extract(query, model) → with_structured_output，1 次 LLM

Step 2: 规则路由 + 并行检索
  ├── 只提到设备 → graph
  ├── 只提到法规 → vector
  └── 通用/混合 → hybrid（vector + bm25 + graph）
  并行执行：ThreadPoolExecutor

Step 3: context_fusion.py
  ├── 实体去重（按 doc_id，复用 _rrf_merge 的去重逻辑）
  ├── RRF 三路融合（bm25 + dense + graph）
  ├── 父文档回填（已实现）
  └── Token 预算截断（已实现）

Step 4: LLM 生成
  ├── 拼接带来源编号的上下文
  └── 要求回答标注来源引用

Step 5: RAGAS 评估（可选，默认关闭）
```

### 4.5 MCP 工具体系（Mock 可用，待真实化）

```
当前 11 个工具全部 Mock：

P0 — 知识检索（Phase 2-3 真实化）
  ├── graph_rag_search   → Phase 3 接入 orchestrator
  ├── knowledge_search   → Phase 2 接入 VectorRetriever
  └── graph_query        → Phase 3 接入 GraphTraverser

P0 — 高层工具（Phase 4 接 Java 后端）
  ├── fire_report_generate   → Java /reports/generate
  └── fire_quality_evaluate  → Java /quality/evaluate

P1 — 明细工具（Phase 4 接 Java 后端）
  ├── fire_equipment_query
  ├── fire_alarm_record_query
  ├── fire_inspection_query
  ├── fire_maintenance_order_query
  ├── fire_duty_schedule_query
  └── fire_utility_monitor_query
```

---

## 五、目录结构（当前实际，非设计文档版）

```
src/
├── agent/                              # ✅ 85% 完成
│   ├── main_agent.py                   # ✅ 完整（需修子Agent名称匹配）
│   ├── config.py                       # ✅ 完整
│   ├── llm_config.py                   # ✅ 完整
│   ├── env_utils.py                    # ✅ 完整
│   ├── schema.py                       # ✅ 完整（FireLogisticsContext等）
│   ├── mcp_tools_bean.py               # ✅ 完整（11个工具的Pydantic模型）
│   ├── middleware_config.py            # ✅ 完整
│   ├── memory/prompts.py               # ✅ 完整
│   ├── memory/AGENTS.md                # ⚠️ 内容很少
│   ├── backends/custom_opensandbox.py  # ✅ 完整
│   ├── backends/sandbox_setup.py       # ✅ 完整
│   ├── middlewares/context_injection.py # ✅ 完整
│   ├── middlewares/memory_update.py    # ✅ 完整（仍用手动JSON解析，优化在后）
│   ├── middlewares/tools_summarization.py # ✅ 完整
│   ├── subagents/read_yaml.py          # ✅ 完整
│   ├── subagents/agents/fire_qa_assistant.yaml # ✅ 完整
│   ├── subagents/agents/fire_management_analyst.yaml # ✅ 完整
│   └── tools/MCP_client.py             # ✅ 完整
│
├── graph_rag/                          # ⚠️ 75% 完成
│   ├── config.py                       # ⚠️ 骨架（docstring 描述完整配置项，待实现 pydantic-settings）
│   ├── orchestrator.py                 # ✅ 五步管线实现（实体抽取→并行检索→去重融合→结果持久化）
│   ├── entity_extractor.py             # ✅ LLM+NER 并行抽取 + 融合去重完整
│   ├── graph_traverser.py              # ✅ 三级降级路由实现（模板→类型反查→LLM生成）
│   ├── evaluator.py                    # ⚠️ 骨架（retrieval_evaluator.py 已实现判空 fallback）
│   ├── vector_retriever.py             # ✅ 完整
│   ├── context_fusion.py              # ✅ 完整（去重/排序/父文档回填/Token截断）
│   ├── json_save.py                    # ✅ 异步 JSON 持久化
│   ├── rule_extractors.py              # ✅ 条款号正则抽取
│   ├── retrieval_evaluator.py          # ✅ 检索结果判空 + fallback 机制
│   ├── graph_db/connection.py          # ✅ 完整
│   ├── graph_db/schema.py              # ✅ 完整
│   ├── graph_db/queries.py             # ✅ 3种Cypher模板 + LLM动态查询
│   ├── graph_db/writer.py              # ✅ UNWIND+MERGE批量写入
│   ├── vector_db/collections.py        # ✅ 完整
│   ├── vector_db/db_operator.py        # ⚠️ 70%（有bug，逐条INSERT待优化）
│   ├── vector_db/db_retriever.py       # ✅ 完整
│   └── ingestion/                      # ⚠️ 70% 完成
│       ├── doc_parser/
│       │   ├── md_parser.py            # ✅ Markdown解析+元数据增强
│       │   ├── dispatcher.py           # ❌ 骨架（路由规则文档化）
│       │   ├── pdf_parser.py           # ❌ 骨架（DotsOCR/PyMuPDF方案）
│       │   ├── office_parser.py        # ❌ 骨架（Unstructured方案）
│       │   └── image_parser.py         # ❌ 骨架（OCR+多模态描述方案）
│       ├── splitter.py                 # ✅ 标题切分+语义二次切分+图片分离
│       ├── embedding.py                # ✅ HuggingFace bge-small-zh-v1.5
│       ├── entity_relation_extractor.py # ✅ 文档级实体抽取+Neo4j写入
│       ├── biz_sync.py                 # ❌ 骨架（Java后端数据同步）
│       └── save_data.py                # ✅ 入库编排顶层入口
├── mcp_server/                         # ⚠️ 70% 完成
│   ├── server_main.py                  # ✅ 完整
│   ├── server_config.py                # ✅ 完整
│   ├── http_base.py                    # ✅ 完整
│   └── tools/                          # ⚠️ 全部 Mock
│       ├── knowledge_tools.py          # Mock → Phase 2-3 真实化
│       ├── report_tools.py             # Mock → Phase 4 真实化
│       ├── fire_equipment_tools.py     # Mock → Phase 4 真实化
│       ├── fire_alarm_tools.py         # Mock → Phase 4 真实化
│       ├── fire_inspection_tools.py    # Mock → Phase 4 真实化
│       ├── fire_maintenance_tools.py   # Mock → Phase 4 真实化
│       ├── fire_duty_tools.py          # Mock → Phase 4 真实化
│       └── fire_utility_tools.py       # Mock → Phase 4 真实化
│
├── api_view/                           # ❌ 空
├── test/                               # ✅ 70% 覆盖
└── util_tools/logger.py               # ✅ 完整
```

---

## 六、优化方案（主流程跑通后逐步实施）

> 以下为设计文档中规划但当前不阻塞主流程的优化项，按优先级排列。

### P1 — 代码质量（主流程跑通后立即做）

| # | 优化项 | 来源 | 说明 |
|---|--------|------|------|
| 1 | `memory_update.py` 用 `with_structured_output` 替代手动 JSON 解析 | 设计文档 5.4 节 | 当前手动 `json.loads(text[start:end+1])` 脆弱 |
| 2 | `memory_update.py` 偏好存储用 Pydantic 序列化替代 Markdown 手动解析 | 设计文档 5.7 节 | 当前 `_merge_preferences` 60+ 行 Markdown 解析 |
| 3 | `db_operator.py` 凭据外部化 | 本次审查 | 硬编码密码 → config/env |
| 4 | 提示模板外部化 | 设计文档 middleware-optimization | 硬编码提示 → Jinja2 模板 |
| 5 | `db_retriever.py` 参数命名统一 | 本次审查 | `top_K` → `top_k` |

### P2 — 架构优化（稳定运行后做）

| # | 优化项 | 来源 | 说明 |
|---|--------|------|------|
| 1 | Store 持久化：InMemoryStore → MongoDBStore/PostgresStore | 设计文档 | 重启丢失用户偏好 |
| 2 | 关键词列表外部化（config.yaml） | 设计文档 | 当前硬编码在 `memory_update.py` |
| 3 | RAGAS 评估接入 | 设计文档 | 问答质量可度量 |
| 4 | LangSmith 可观测性 | 设计文档 | Agent 运行追踪 |
| 5 | Reranker 精排 | 设计文档 db_retriever | RRF 粗排后加交叉编码器 |

### P3 — 远期规划（业务验证后做）

| # | 优化项 | 来源 | 说明 |
|---|--------|------|------|
| 1 | Embedding 模型升级：bge-small-zh → bge-m3 / DashScope | 设计文档 | 效果对比后再决定 |
| 2 | 文档自动入库管线完善 | 设计文档 | PDF/Office/图片全格式 |
| 3 | 业务数据自动同步（biz_sync） | 设计文档 | Java DB → Neo4j 增量同步 |
| 4 | 文档→图自动抽取（entity_relation_extractor） | 设计文档 | LLM 抽取实体关系写入 Neo4j |
| 5 | Multi-Agent 编排升级 | 设计文档 | YAML → LangGraph 图编排 |
| 6 | 安全护栏（Guardrails AI） | 设计文档 | 输入/输出安全校验 |

---

## 七、关键技术决策记录

| 决策 | 选择 | 理由 | 备注 |
|------|------|------|------|
| 向量数据库 | PostgreSQL + pgvector | 比 Milvus 轻量，无需额外部署；项目已有 PG | 设计文档原定 Milvus，实际已改 |
| Embedding 模型 | BAAI/bge-small-zh-v1.5 (512维) | 本地部署，无需 API；中文效果好 | 后续可升级 bge-m3 或 DashScope |
| 图数据库 | Neo4j | 设计文档一致，Cypher 表达力强 | |
| BM25 实现 | jieba + rank_bm25（Python 端） | 不依赖 PG 全文检索；中文分词灵活 | 设计文档一致 |
| 检索融合 | RRF (k=60) | 设计文档一致；C9 项目验证有效 | |
| 知识工具 Mock 策略 | 先 Mock 跑通主流程，逐步替换 | 降低耦合，分阶段验证 | |
| 对话历史 Collection | 暂不建 fire_context_collection | 短期不需要，Agent Checkpoint 已覆盖 | 可后续补充 |
| 文档入库范围 | Phase 2 只支持 Markdown | 最快跑通；PDF/Office 后续扩展 | |

---

## 八、风险与依赖

| 风险 | 影响 | 应对 |
|------|------|------|
| OpenSandbox 不可用 | 主 Agent 创建失败 | Phase 1 可临时跳过沙箱，用 Mock Backend |
| MongoDB 不可用 | Checkpoint 无法持久化 | 临时用 MemorySaver 替代 |
| Java 后端 API 未就绪 | 6个明细工具+2个高层工具无法真实化 | Phase 1-3 不依赖 Java，Mock 即可 |
| Neo4j 未部署 | 图遍历无法使用 | Phase 2 只用向量检索，Phase 3 才需要 Neo4j |
| PG 未部署 | 向量检索无法使用 | Phase 1 用 Mock，Phase 2 前需部署 PG |

---

## 九、与旧设计文档的关系

本文档**不替代**旧设计文档，而是**补充**执行层指导：

| 旧文档 | 定位 | 本文档定位 |
|--------|------|-----------|
| `graph-rag-architecture.md` | **完整架构设计**（13章节，含所有模块的设计意图、数据流、接口定义） | **执行路线图**（基于现状的优先级排序和实施步骤） |
| `graph-rag-optimization.md` | **优化方案**（C9经验、实现细节、防坑指南） | **参考**（Phase 3 实现编排器时复用其细节） |
| `project-architecture.md` | **原始采购项目架构**（已过时，被 graph-rag-architecture.md 取代） | **历史参考** |
| `middleware-optimization.md` | **中间件优化方案** | **P1优化参考**（主流程跑通后逐步实施） |
| `agent-context-guide.md` | **概念指南**（state/runtime 区别） | **知识库**（开发时参考） |

**实施过程中，架构细节以 `graph-rag-architecture.md` 为准，优先级和步骤以本文档为准。**
