# 消防后勤智能助手 — 项目概览

> 文档生成日期：2026-07-08  
> 基于 `src/implementation-roadmap.md` 最新数据

---

## 一、项目概述

**消防后勤智能助手**（FireAgentSystem）是基于 LangGraph 构建的消防安全领域智能问答与管理分析系统。它结合多智能体编排、GraphRAG 知识检索和 MCP 工具服务，为消防管理人员提供法规查询、设备管理、巡检报表等一站式智能服务。

**核心定位**：让消防领域的知识检索和业务查询从"翻文档"变为"问 AI"。

---

## 二、系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                        用户交互层                            │
│              (CLI / API / 未来 Web 前端)                     │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────┐
│                    Agent 主流程层                            │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    │
│   │  主 Agent   │───→│  中间件链   │───→│  子 Agent   │    │
│   │ (路由分发)  │    │(上下文注入/ │    │(问答/管理)  │    │
│   │             │    │ 记忆更新/  │    │             │    │
│   │             │    │ 工具摘要)   │    │             │    │
│   └─────────────┘    └─────────────┘    └──────┬──────┘    │
└───────────────────────────────────────────────┼───────────┘
                                                │
┌───────────────────────────────────────────────▼───────────┐
│                   MCP Server 层                            │
│   ┌─────────────────┐    ┌──────────────────────────┐   │
│   │   知识检索工具   │    │      业务查询工具         │   │
│   │ • graph_rag_search│   │ • fire_report_generate  │   │
│   │ • knowledge_search│   │ • fire_quality_evaluate │   │
│   │ • graph_query    │    │ • fire_equipment_query  │   │
│   └─────────────────┘    │ • ... (共 11 个工具)      │   │
│                          └──────────────────────────┘   │
└───────────────────────────────────────────┬───────────────┘
                                            │
┌───────────────────────────────────────────▼───────────────┐
│                   GraphRAG 引擎层                          │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│   │  向量检索    │    │   图遍历     │    │   编排器     │ │
│   │(PG+pgvector)│    │  (Neo4j)    │    │(五步管线)   │ │
│   └─────────────┘    └─────────────┘    └─────────────┘ │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│   │  数据入库    │    │  实体抽取    │    │  上下文融合  │ │
│   │(MD/PDF/Office)│   │(LLM+NER)   │    │(RRF+去重)   │ │
│   └─────────────┘    └─────────────┘    └─────────────┘ │
└─────────────────────────────────────────────────────────┘
```

**调用链**：用户提问 → 主 Agent 路由 → 子 Agent 选择 → MCP 工具调用 → GraphRAG 检索 / Java 后端查询 → 结果返回

---

## 三、各模块完成度

| 模块 | 完成度 | 状态 | 说明 |
|------|--------|------|------|
| **Agent 主流程** | 85% | 🟢 | `main_agent.py` 完整，子 Agent YAML 配置完整，中间件链完整 |
| **MCP Server 框架** | 70% | 🟡 | Server + HTTP 基础 + 工具注册完整，工具仍为 Mock |
| **MCP 工具定义** | 90% | 🟢 | 11 个工具全部注册，Pydantic 模型完整 |
| **中间件** | 80% | 🟡 | 3 个中间件全部实现；`memory_update` 仍用手动 JSON 解析 |
| **GraphRAG 向量检索** | 90% | 🟢 | PGVector + HybridRetrieval + VectorRetriever + ContextFusion 全部实现 |
| **GraphRAG 图数据库** | 85% | 🟢 | Neo4jDriver + schema + queries + writer + graph_traverser 完成 |
| **GraphRAG 编排层** | 75% | 🟡 | 五步管线已实现，存在硬编码连接参数和每次请求重建实例问题 |
| **GraphRAG 实体抽取** | 95% | 🟢 | LLM+NER 并行抽取 + 融合去重完整 |
| **数据入库管线** | 70% | 🟡 | md_parser + splitter + embedding + db_operator 已实现；PDF/Office/图片仍为骨架 |
| **项目入口** | 0% | 🔴 | `run.py` 只有 docstring，无实际代码 |
| **测试** | 70% | 🟡 | Schema / MCP Tools / Middleware / SubAgent / E2E Phase1 已覆盖 |

---

## 四、已完成的核心功能

### Agent 层
- ✅ 主 Agent 路由与分发逻辑（`main_agent.py`）
- ✅ 子 Agent YAML 配置与加载（问答助手 + 管理分析师）
- ✅ 中间件链：上下文注入、记忆更新、工具摘要、调用限流
- ✅ LLM 配置与 CompositeBackend 分流
- ✅ MCP 工具 Pydantic 数据模型（`mcp_tools_bean.py`）
- ✅ 用户偏好存储（StoreBackend）

### GraphRAG 层
- ✅ PGVector 向量数据库管理（连接、建表、Embedding）
- ✅ HybridRetrieval 混合检索（dense + BM25 + hybrid + RRF）
- ✅ VectorRetriever 统一检索入口（父文档回填、Token 截断）
- ✅ ContextFusion 上下文融合（去重、排序、回填、截断）
- ✅ Neo4j 图数据库连接与 Schema 定义（11 种节点）
- ✅ 参数化 Cypher 查询模板（3 种：设备依赖、区域法规、模块导航）
- ✅ GraphTraverser 三级降级路由（模板 → 类型反查 → LLM 生成）
- ✅ EntityExtractor 双路径抽取（jieba 快速 / LLM 结构化）
- ✅ Orchestrator 五步管线（实体抽取 → 并行检索 → 去重融合 → LLM 生成 → 评估）
- ✅ Markdown 文档解析与入库管线
- ✅ 批量数据写入（UNWIND + MERGE）

### MCP Server 层
- ✅ FastMCP 服务框架（`server_main.py`）
- ✅ HTTP 客户端基础（`http_base.py`）
- ✅ 11 个工具注册与 Mock 返回结构

### 测试
- ✅ Schema 验证测试
- ✅ MCP Tools Bean 测试
- ✅ 中间件测试
- ✅ 子 Agent 测试
- ✅ E2E Phase1 测试

---

## 五、待完成的功能

### 🔴 阻塞性（影响主流程跑通）
- ❌ `run.py` 项目入口实现（CLI 对话 + MCP Server 启动）
- ❌ `api_view/` API 视图层（FastAPI 最小实现）
- ❌ MCP Server 与 Agent 端联调验证

### ⚠️ 高优先级（Phase 4）
- ⚠️ 6 个明细工具 + 2 个高层工具从 Mock 替换为真实 Java 后端 API 调用
- ⚠️ `db_operator.py` 硬编码凭据外部化（config/env）
- ⚠️ `main_agent.py` 子 Agent 名称匹配 Bug 修复

### ⚠️ 中优先级（优化项）
- ⚠️ `memory_update.py` 手动 JSON 解析 → `with_structured_output`
- ⚠️ `memory_update.py` Markdown 手动解析 → Pydantic 序列化
- ⚠️ `db_operator.py` 逐条 INSERT → 批量插入优化
- ⚠️ PDF / Office / 图片文档解析器实现
- ⚠️ 提示模板外部化（Jinja2）

### ⚠️ 低优先级（远期规划）
- ⚠️ Store 持久化：InMemoryStore → MongoDBStore/PostgresStore
- ⚠️ RAGAS 评估接入
- ⚠️ LangSmith 可观测性
- ⚠️ Reranker 精排（交叉编码器）
- ⚠️ Embedding 模型升级（bge-small-zh → bge-m3 / DashScope）
- ⚠️ 业务数据自动同步（biz_sync）
- ⚠️ 文档→图自动抽取（entity_relation_extractor）
- ⚠️ Multi-Agent 图编排升级（YAML → LangGraph）
- ⚠️ 安全护栏（Guardrails AI）

---

## 六、技术栈

| 类别 | 技术 | 说明 |
|------|------|------|
| **智能体框架** | LangGraph / LangChain | 多轮对话、子 Agent 委派、状态管理 |
| **MCP 服务** | FastMCP | 工具暴露与调用 |
| **向量数据库** | PostgreSQL + pgvector | 轻量、运维简单 |
| **图数据库** | Neo4j | Cypher 表达力强 |
| **Embedding** | HuggingFace `BAAI/bge-small-zh-v1.5` | 512 维，本地部署 |
| **LLM** | OpenSandbox | 主 Agent 推理 |
| **API 框架** | FastAPI（计划） | REST + SSE 流式 |
| **测试** | pytest + pytest-asyncio | 异步测试支持 |
| **语言** | Python 3.13+ | 类型提示 |

---

## 七、项目目录结构

```
src/
├── agent/                    # 核心智能体框架
│   ├── main_agent.py         # 主 Agent 路由与分发
│   ├── config.py             # Agent 配置
│   ├── llm_config.py         # LLM 配置
│   ├── schema.py             # 数据模型
│   ├── mcp_tools_bean.py     # MCP 工具 Pydantic 模型
│   ├── middleware_config.py  # 中间件配置
│   ├── memory/               # 记忆模块
│   ├── backends/             # 后端实现（OpenSandbox）
│   ├── middlewares/          # 中间件（上下文注入/记忆更新/工具摘要）
│   ├── subagents/            # 子 Agent 配置与加载
│   └── tools/                # 工具（MCP 客户端等）
│
├── graph_rag/                # GraphRAG 模块
│   ├── config.py             # GraphRAG 配置（骨架）
│   ├── orchestrator.py       # 编排器（五步管线）
│   ├── entity_extractor.py   # 实体抽取
│   ├── graph_traverser.py    # 图遍历
│   ├── vector_retriever.py   # 向量检索入口
│   ├── context_fusion.py     # 上下文融合
│   ├── json_save.py          # JSON 持久化
│   ├── rule_extractors.py    # 规则抽取
│   ├── retrieval_evaluator.py # 检索评估
│   ├── graph_db/             # 图数据库（Neo4j）
│   ├── vector_db/            # 向量数据库（PG + pgvector）
│   └── ingestion/            # 数据入库管线
│       ├── doc_parser/       # 文档解析（MD/PDF/Office/图片）
│       ├── splitter.py       # 文本切分
│       ├── embedding.py      # Embedding 生成
│       └── save_data.py      # 入库编排
│
├── mcp_server/               # MCP 服务器
│   ├── server_main.py        # FastMCP 服务入口
│   ├── server_config.py      # Server 配置
│   ├── http_base.py          # HTTP 客户端基础
│   └── tools/                # 11 个消防领域工具
│
├── api_view/                 # API 视图层（空）
├── test/                     # 测试套件
└── util_tools/               # 共享工具（日志等）
```

---

## 八、下一步工作计划

### Phase 0：修复阻塞性 Bug（1 天）
1. 修复 `main_agent.py` 子 Agent 名称匹配逻辑
2. 修复 `db_operator.py` logger bug 和硬编码凭据
3. 统一 DDL 中 vector 维度文档

### Phase 1：主流程端到端跑通（3-5 天）
1. 实现 `run.py` 项目入口（Agent CLI + MCP Server 模式）
2. 实现最小 API 视图层（FastAPI：POST /chat、GET /sessions、SSE /stream）
3. MCP Server 与 Agent 端联调验证
4. 关键配置确认（MCP_SERVER_URL、MongoDB、OpenSandbox）

### Phase 2-3：GraphRAG 真实化（已完成）
- ✅ 向量检索真实化（PG + pgvector）
- ✅ 图遍历 + 编排器实现（Neo4j + 五步管线）
- ✅ 知识库数据准备与测试

### Phase 4：MCP 工具真实化（待开始）
1. Java 后端 API 联调（6 个明细工具 + 2 个高层工具）
2. 数据入库管线扩展（PDF / Office / 图片解析）

### 优化项（主流程跑通后逐步实施）
- P1：代码质量（memory_update 结构化输出、db_operator 批量插入、提示模板外部化）
- P2：架构优化（Store 持久化、RAGAS 评估、LangSmith 可观测性、Reranker 精排）
- P3：远期规划（Embedding 升级、文档自动入库、业务数据同步、Multi-Agent 图编排）

---

## 附录：关键技术决策

| 决策 | 选择 | 理由 |
|------|------|------|
| 向量数据库 | PostgreSQL + pgvector | 比 Milvus 轻量，无需额外部署 |
| Embedding 模型 | BAAI/bge-small-zh-v1.5 (512 维) | 本地部署，无需 API；中文效果好 |
| 图数据库 | Neo4j | Cypher 表达力强 |
| BM25 实现 | jieba + rank_bm25（Python 端） | 不依赖 PG 全文检索；中文分词灵活 |
| 检索融合 | RRF (k=60) | C9 项目验证有效 |
| 知识工具策略 | 先 Mock 跑通主流程，逐步替换 | 降低耦合，分阶段验证 |
| 文档入库范围 | Phase 2 只支持 Markdown | 最快跑通；PDF/Office 后续扩展 |

---

> **注意**：本文档基于 `src/implementation-roadmap.md` 生成，实施过程中请以最新版 roadmap 为准。
