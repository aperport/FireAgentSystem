# FireAgentSystem 项目全面梳理

> 生成日期：2026-08-05
> 基于 `feature/dev` 分支最新代码（commit a138f86）

---

## 一、项目概述

**消防后勤智能助手**（FireAgentSystem）是基于 LangGraph 构建的消防安全领域智能问答与管理分析系统。

**核心定位**：让消防领域的知识检索和业务查询从"翻文档"变为"问 AI"。

**技术栈**：Python 3.13+ / LangGraph / LangChain / FastMCP / PostgreSQL+pgvector / Neo4j / HuggingFace Embeddings / DeepSeek LLM

---

## 二、完整目录结构

```
DeepAgentsDemo2/
├── run.py                           # 统一入口（agent/mcp-server/api 三模式）
├── requirements.txt                 # 73 行依赖
├── AGENTS.md                        # 仓库贡献指南
├── project-overview.md              # 项目概览（旧版，部分过时）
│
├── data/
│   └── T20260706.json               # GraphRAG 查询结果样例
│
├── docs/
│   ├── 消防法.md                     # 消防法规参考文档
│   ├── bug-audit-20260712.md        # Bug 审计记录
│   ├── evaluation-standard-design.md # 评价标准设计 + Agent 应用场景
│   ├── local-opensandbox-setup.md   # OpenSandbox 本地部署指南
│   └── sandbox-audit-20260714.md    # Sandbox 审计记录
│
└── src/
    ├── implementation-roadmap.md    # 实施路线图（详细，635 行）
    │
    ├── agent/                       # 核心智能体框架
    │   ├── config.py                # 路径、Store、Checkpoint、模型配置
    │   ├── llm_config.py            # DeepSeek LLM 实例（主模型 + 快速模型）
    │   ├── main_agent.py            # 主 Agent 创建管线、_AgentProxy 懒加载
    │   ├── schema.py                # 15 个 Pydantic/dataclass 数据模型
    │   ├── mcp_tools_bean.py        # 11 个 MCP 工具的 Pydantic 模型（8 组）
    │   ├── middleware_config.py      # 子 Agent 中间件工厂
    │   ├── backends/
    │   │   ├── custom_opensandbox.py # OpenSandbox 后端适配器
    │   │   └── sandbox_setup.py     # Sandbox 初始化、技能上传
    │   ├── middlewares/
    │   │   ├── context_injection.py # 上下文注入中间件（before_agent）
    │   │   ├── memory_update.py     # 记忆更新中间件（aafter_agent）
    │   │   └── tools_summarization.py # 工具摘要中间件
    │   ├── memory/
    │   │   ├── AGENTS.md            # Agent 行为规则（257 行）
    │   │   └── prompts.py           # 主 Agent system_prompt
    │   ├── subagents/
    │   │   ├── read_yaml.py         # YAML 加载、工具解析、子 Agent 组装
    │   │   └── agents/
    │   │       ├── fire_qa_assistant.yaml        # 问答助手配置（3 知识工具）
    │   │       └── fire_management_analyst.yaml  # 管理分析师配置（9 工具）
    │   └── tools/
    │       └── MCP_client.py        # MCP Server 连接与工具加载
    │
    ├── graph_rag/                   # GraphRAG 检索引擎
    │   ├── config.py                # ❌ 骨架：仅 docstring
    │   ├── orchestrator.py          # 五步管线编排器
    │   ├── entity_extractor.py      # LLM+NER 并行实体抽取
    │   ├── context_fusion.py        # 上下文融合（去重/排序/回填/截断）
    │   ├── graph_traverser.py       # 图遍历（三级降级路由）
    │   ├── vector_retriever.py      # 向量检索统一入口
    │   ├── evaluator.py             # RAGAS 评估器（未集成）
    │   ├── retrieval_evaluator.py   # 检索结果判空 + fallback（未集成）
    │   ├── rule_extractors.py       # 条款号正则抽取
    │   ├── json_save.py             # 异步 JSON 持久化
    │   ├── graph_db/
    │   │   ├── connection.py        # Neo4j 双驱动（同步+异步）
    │   │   ├── schema.py            # 11 节点类型 + 11 关系类型 + dataclass
    │   │   ├── queries.py           # 3 Cypher 模板 + LLM 动态查询
    │   │   ├── writer.py            # UNWIND+MERGE 批量写入
    │   │   └── graph_vector_traverser.py # 实体扩散+向量精排（新增）
    │   ├── vector_db/
    │   │   ├── collections.py       # PGVectorManager + DDL + SQL 模板
    │   │   ├── db_operator.py       # 数据写入（逐行 INSERT）
    │   │   └── db_retriever.py      # 混合检索（dense/BM25/hybrid + RRF）
    │   └── ingestion/
    │       ├── __init__.py          # 导出 ingest_markdown, ingest_directory
    │       ├── save_data.py         # 入库编排顶层入口
    │       ├── splitter.py          # Markdown 标题切分 + 语义二次切分
    │       ├── embedding.py         # HuggingFace Embedding 封装
    │       ├── entity_relation_extractor.py # 文档级实体抽取 + Neo4j 写入
    │       ├── biz_sync.py          # ❌ 骨架：Java→Neo4j 数据同步
    │       └── doc_parser/
    │           ├── __init__.py      # ParsedDocument dataclass
    │           ├── md_parser.py     # Markdown 解析 + 元数据增强
    │           ├── dispatcher.py    # ❌ 骨架：格式路由
    │           ├── pdf_parser.py    # ❌ 骨架：PDF 解析
    │           ├── image_parser.py  # ❌ 骨架：图片解析
    │           └── office_parser.py # ❌ 骨架：Office 解析
    │
    ├── mcp_server/                  # MCP 工具服务
    │   ├── server_main.py           # FastMCP 入口，注册 8 组工具
    │   ├── server_config.py         # Java API URL、MCP Host/Port/Path
    │   ├── http_base.py             # httpx.AsyncClient 生命周期
    │   └── tools/
    │       ├── knowledge_tools.py   # ✅ 真实 GraphRAG（3 工具）
    │       ├── report_tools.py      # 🔶 Mock（2 工具：报表+评鉴）
    │       ├── fire_equipment_tools.py   # 🔶 Mock
    │       ├── fire_alarm_tools.py       # 🔶 Mock
    │       ├── fire_inspection_tools.py  # 🔶 Mock
    │       ├── fire_maintenance_tools.py # 🔶 Mock
    │       ├── fire_duty_tools.py        # 🔶 Mock
    │       └── fire_utility_tools.py     # 🔶 Mock
    │
    ├── api_view/                    # HTTP API 层
    │   └── servers.py               # FastAPI：仅 POST /talk
    │
    ├── test/                        # 测试套件
    │   ├── conftest.py              # 共享 fixtures
    │   ├── test_schema.py           # Schema 模型测试
    │   ├── test_mcp_tools_bean.py   # MCP 工具 Bean 测试
    │   ├── test_mcp_tools.py        # ⚠️ MCP 工具测试（有失效导入）
    │   ├── test_middlewares.py      # 中间件测试
    │   ├── test_subagents.py        # 子 Agent 测试
    │   └── test_e2e_phase1.py       # E2E Phase1 测试
    │
    └── util_tools/
        └── logger.py                # loguru 代理
```

---

## 三、模块完成度

| 模块 | 完成度 | 状态 | 说明 |
|------|--------|------|------|
| **Agent 主流程** | 85% | 🟢 | 主 Agent 管线完整，子 Agent 配置完整，中间件链完整 |
| **MCP Server 框架** | 70% | 🟡 | 框架完整，3/11 工具已真实化，8/11 仍为 Mock |
| **GraphRAG 查询** | 90% | 🟢 | 五步管线 + 混合检索 + 图遍历 + 融合完整 |
| **GraphRAG 入库** | 70% | 🟡 | Markdown 入库完整，PDF/Office/图片仍为骨架 |
| **GraphRAG 评估** | 80% | 🟡 | RAGAS + 检索评估已实现，但未集成到编排器 |
| **API 层** | 10% | 🔴 | 仅 1 个 POST /talk 端点，无会话管理/SSE |
| **配置管理** | 30% | 🔴 | graph_rag/config.py 为骨架，多处硬编码 |
| **测试** | 65% | 🟡 | 核心模块已覆盖，test_mcp_tools.py 有失效导入 |

---

## 四、各模块详细状态

### 4.1 Agent 主流程（85%）

**调用链**：用户提问 → 主 Agent 路由 → 子 Agent 委派 → MCP 工具调用 → 结果返回

| 组件 | 文件 | 状态 | 备注 |
|------|------|------|------|
| 主 Agent 创建 | `main_agent.py` | ✅ | 9 步创建管线，_AgentProxy 懒加载 |
| LLM 配置 | `llm_config.py` | ✅ | DeepSeek 主模型 + 快速模型 |
| 数据模型 | `schema.py` | ✅ | 15 个模型，含 SSE 事件定义 |
| MCP 工具模型 | `mcp_tools_bean.py` | ✅ | 8 组 ~25 个 Pydantic 模型 |
| 上下文注入 | `context_injection.py` | ✅ | before_agent 注入 user_id |
| 记忆更新 | `memory_update.py` | ⚠️ | 手动 JSON 解析，脆弱 |
| 工具摘要 | `tools_summarization.py` | ✅ | 自动触发 |
| 子 Agent 加载 | `read_yaml.py` | ⚠️ | `_validate_subagent_config` 拒绝 dict 格式 tools |
| MCP 客户端 | `MCP_client.py` | ✅ | MultiServerMCPClient 连接 |
| Sandbox 后端 | `custom_opensandbox.py` | ✅ | 需 OpenSandbox API Key |

**已知问题**：
- `memory_update.py` 用 `json.loads(text[start:end+1])` 手动解析 LLM 输出，应改用 `with_structured_output`
- `read_yaml.py` 的 `_validate_subagent_config` 检查 `isinstance(tools, list)`，但 YAML 用 dict 格式

### 4.2 GraphRAG 查询管线（90%）

**五步管线**：实体抽取 → 并行检索（向量+图） → 上下文融合 → LLM 生成 → 评估

| 组件 | 文件 | 状态 | 备注 |
|------|------|------|------|
| 编排器 | `orchestrator.py` | ✅ | 五步管线完整，硬编码 PG 连接参数 |
| 实体抽取 | `entity_extractor.py` | ✅ | LLM+NER 并行抽取 + 融合去重 |
| 向量检索 | `vector_retriever.py` | ✅ | dense/sparse/hybrid + asyncio.to_thread |
| 图遍历 | `graph_traverser.py` | ⚠️ | 三级降级路由，但只处理第一个实体 |
| 图向量融合 | `graph_vector_traverser.py` | ✅ | 新增：实体扩散 + 向量精排 |
| 上下文融合 | `context_fusion.py` | ✅ | 去重/排序/父文档回填/Token 截断 |
| 混合检索 | `db_retriever.py` | ✅ | dense/BM25/hybrid + RRF(k=60) |
| RAGAS 评估 | `evaluator.py` | ✅ | 5 指标评估，未集成到编排器 |
| 检索评估 | `retrieval_evaluator.py` | ✅ | 判空 + fallback，未集成到编排器 |

**已知问题**：
- `graph_traverser.py` 的 `traverse()` 循环内 `return`，只处理第一个实体
- `orchestrator.py` 硬编码 `os.getenv("PG_PASSWORD", "1")`
- `evaluator.py` 和 `retrieval_evaluator.py` 已实现但未接入编排器

### 4.3 GraphRAG 入库管线（70%）

**管线**：文档解析 → 切分 → Embedding → PG 写入 → 实体抽取 → Neo4j 写入

| 组件 | 文件 | 状态 | 备注 |
|------|------|------|------|
| Markdown 解析 | `md_parser.py` | ✅ | 解析 + 元数据增强 + 图片提取 |
| 文本切分 | `splitter.py` | ✅ | 标题切分 + 语义二次切分 |
| Embedding | `embedding.py` | ✅ | HuggingFace bge-small-zh-v1.5 |
| PG 写入 | `db_operator.py` | ⚠️ | 逐行 INSERT，硬编码密码 |
| 实体抽取 | `entity_relation_extractor.py` | ✅ | 文档级抽取 + Neo4j 写入 |
| 入库编排 | `save_data.py` | ✅ | ingest_markdown(), ingest_directory() |
| PDF 解析 | `pdf_parser.py` | ❌ | 骨架 |
| Office 解析 | `office_parser.py` | ❌ | 骨架 |
| 图片解析 | `image_parser.py` | ❌ | 骨架 |
| 格式路由 | `dispatcher.py` | ❌ | 骨架 |
| 业务同步 | `biz_sync.py` | ❌ | 骨架 |

### 4.4 MCP Server（70%）

| 工具 | 文件 | 数据源 | 状态 |
|------|------|--------|------|
| `graph_rag_search` | `knowledge_tools.py` | 真实 GraphRAG | ✅ |
| `knowledge_search` | `knowledge_tools.py` | 真实 VectorRetriever | ✅ |
| `graph_query` | `knowledge_tools.py` | 真实 GraphTraverser | ✅ |
| `fire_report_generate` | `report_tools.py` | Mock | 🔶 |
| `fire_quality_evaluate` | `report_tools.py` | Mock | 🔶 |
| `fire_equipment_query` | `fire_equipment_tools.py` | Mock | 🔶 |
| `fire_alarm_record_query` | `fire_alarm_tools.py` | Mock | 🔶 |
| `fire_inspection_query` | `fire_inspection_tools.py` | Mock | 🔶 |
| `fire_maintenance_order_query` | `fire_maintenance_tools.py` | Mock | 🔶 |
| `fire_duty_schedule_query` | `fire_duty_tools.py` | Mock | 🔶 |
| `fire_utility_monitor_query` | `fire_utility_tools.py` | Mock | 🔶 |

### 4.5 API 层（10%）

| 端点 | 方法 | 状态 | 备注 |
|------|------|------|------|
| `/talk` | POST | ✅ | 基础对话，无会话管理 |
| `/sessions` | GET | ❌ | schema.py 已定义但未实现 |
| `/stream/{id}` | SSE | ❌ | schema.py 已定义 SSE 事件模型 |

### 4.6 测试（65%）

| 测试文件 | 覆盖范围 | 状态 | 备注 |
|---------|---------|------|------|
| `test_schema.py` | 15 个数据模型 | ✅ | |
| `test_mcp_tools_bean.py` | 8 组 Pydantic 模型 | ✅ | |
| `test_mcp_tools.py` | 11 个 MCP 工具 | ❌ | 导入已删除的 Mock 常量 |
| `test_middlewares.py` | 3 个中间件 | ✅ | |
| `test_subagents.py` | YAML 加载 + 组装 | ✅ | 记录了 validate bug |
| `test_e2e_phase1.py` | E2E 集成 | ✅ | |

---

## 五、已知 Bug 与问题

### 🔴 阻塞性

| # | 问题 | 文件 | 影响 |
|---|------|------|------|
| 1 | `test_mcp_tools.py` 导入已删除的 `_MOCK_KNOWLEDGE_DOCS` / `_MOCK_GRAPH_PATHS` | `test/test_mcp_tools.py:31` | 测试无法运行 |
| 2 | `_validate_subagent_config` 拒绝 dict 格式 tools | `subagents/read_yaml.py` | `load_yaml()` 返回空列表 |

### 🟡 需修复

| # | 问题 | 文件 | 影响 |
|---|------|------|------|
| 3 | `graph_traverser.py` traverse() 只处理第一个实体 | `graph_traverser.py` | 多实体查询丢失结果 |
| 4 | `orchestrator.py` 硬编码 PG 连接参数 | `orchestrator.py` | 部署不灵活 |
| 5 | `db_operator.py` 硬编码密码 `"NewPass123!"` | `db_operator.py:42` | 安全风险 |
| 6 | `memory_update.py` 手动 JSON 解析 | `memory_update.py` | 脆弱，易崩溃 |
| 7 | `graph_db/writer.py` 模块级实例化 Neo4jDrivers | `writer.py` | import 时连接，.env 未加载 |
| 8 | `collections.py` Embedding 模型/设备硬编码 | `collections.py` | 与 evaluator.py 的 `"cuda"` 不一致 |
| 9 | `evaluator.py` / `retrieval_evaluator.py` 未集成到编排器 | `orchestrator.py` | 评估能力闲置 |
| 10 | `CLAUSE_PATTERNS` 在 `entity_relation_extractor.py` 和 `rule_extractors.py` 重复定义 | 两文件 | 维护不一致风险 |

### 🟢 优化项

| # | 问题 | 文件 | 建议 |
|---|------|------|------|
| 11 | `db_operator.py` 逐行 INSERT | `db_operator.py` | 改为 executemany 批量插入 |
| 12 | `json_save.py` 全局文件锁 | `json_save.py` | 高并发时瓶颈 |
| 13 | API 层仅 1 个端点 | `api_view/servers.py` | 补充会话管理、SSE 流式 |
| 14 | `graph_rag/config.py` 为骨架 | `config.py` | 统一配置管理 |

---

## 六、跨模块依赖关系

```
run.py
├── agent.main_agent (start_main_agent)
│   ├── agent.config (Store, Checkpoint, Model)
│   │   └── agent.llm_config (DeepSeek) ← .env
│   ├── agent.backends.sandbox_setup → custom_opensandbox ← OpenSandbox API
│   ├── agent.tools.MCP_client → MCP Server URL ← .env
│   ├── agent.subagents.read_yaml → YAML configs
│   └── agent.middlewares.* (3 custom + 2 framework)
│
├── mcp_server.server_main (mcp)
│   └── mcp_server.tools.*
│       ├── knowledge_tools → graph_rag.orchestrator → graph_rag.* (真实)
│       └── report_tools, fire_*_tools (Mock → Java 后端)
│
└── api_view.servers (FastAPI app)
    └── agent.main_agent (start_main_agent)
```

**关键耦合点**：
- `knowledge_tools.py` 直接导入 `graph_rag.orchestrator` / `vector_retriever` / `graph_traverser`，GraphRAG 组件初始化失败会导致 MCP Server 无法启动
- `agent.config` 导入 `PostgresSaver`，PG 不可用时整个 agent 模块导入失败
- `graph_db/writer.py` 和 `graph_traverser.py` 模块级实例化 Neo4jDrivers，import 时即连接

---

## 七、运行模式

```bash
# CLI 对话模式
python run.py --mode agent

# MCP Server 模式（供 Agent 调用工具）
python run.py --mode mcp-server

# API Server 模式（HTTP 接口）
python run.py --mode api
```

**外部依赖**：
- PostgreSQL + pgvector（向量存储）
- Neo4j（图数据库）
- OpenSandbox（LLM 沙箱，可选）
- DeepSeek API（LLM 推理）

---

## 八、下一步工作建议

### P0 — 修复阻塞性问题

1. 修复 `test_mcp_tools.py` 失效导入
2. 修复 `_validate_subagent_config` dict 格式兼容
3. 修复 `graph_traverser.py` 只处理第一个实体

### P1 — 核心功能补全

4. 8 个 Mock 工具接入 Java 后端 API
5. API 层补全（会话管理 + SSE 流式）
6. `graph_rag/config.py` 统一配置管理
7. 评估器集成到编排器

### P2 — 代码质量

8. `memory_update.py` 改用 `with_structured_output`
9. `db_operator.py` 批量插入 + 凭据外部化
10. 消除模块级 Neo4j 实例化
11. `CLAUSE_PATTERNS` 提取为公共常量

### P3 — 功能扩展

12. PDF/Office/图片文档解析器
13. Agent 新应用场景（培训生成、合规审查等，见 evaluation-standard-design.md）
14. 业务数据自动同步（biz_sync）
