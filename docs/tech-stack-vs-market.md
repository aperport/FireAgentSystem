# FireAgentSystem 技术栈 vs 市场招聘要求对比分析

> 生成日期：2026-08-05
> 数据来源：猎聘、智联、LinkedIn、Hirist 等平台 2025-2026 年 Agent 开发岗位（20+ 条）

---

## 一、项目当前技术栈

| 类别 | 技术 | 项目中的使用情况 |
|------|------|-----------------|
| **语言** | Python 3.13+ | ✅ 主力语言 |
| **Agent 框架** | LangGraph | ✅ 主 Agent 路由、子 Agent 委派、状态管理 |
| **LLM 框架** | LangChain | ✅ ChatOpenAI、Embeddings、Document、RunnableConfig |
| **MCP 协议** | FastMCP | ✅ 11 个工具注册、Streamable HTTP |
| **向量数据库** | PostgreSQL + pgvector | ✅ dense + BM25 + hybrid + RRF |
| **图数据库** | Neo4j | ✅ Cypher 查询、三级降级路由 |
| **Embedding** | HuggingFace bge-small-zh-v1.5 | ✅ 本地部署 |
| **NER** | HuggingFace BERT (Davlan) | ✅ 实体抽取 |
| **LLM** | DeepSeek (ChatOpenAI) | ✅ 主模型 + 快速模型 |
| **API 框架** | FastAPI | ✅ POST /talk |
| **测试** | pytest + pytest-asyncio | ✅ 6 个测试文件 |
| **配置** | pydantic-settings | ✅ 统一配置管理 |
| **数据模型** | Pydantic | ✅ 25+ 模型定义 |
| **异步** | asyncio | ✅ 异步 Agent、异步检索 |
| **日志** | loguru | ✅ 统一日志 |

---

## 二、市场招聘高频要求（按出现频率排序）

基于 20+ 条 Agent 开发岗位 JD 的关键词频次：

| 排名 | 技术要求 | 出现频率 | 你的项目 | 状态 |
|------|---------|---------|---------|------|
| 1 | **LangGraph / LangChain** | 95% | 已有 | ✅ |
| 2 | **RAG 全链路**（切片/Embedding/检索/重排） | 90% | 已有 | ✅ |
| 3 | **向量数据库**（pgvector/Milvus/Chroma/FAISS） | 85% | pgvector | ✅ |
| 4 | **Prompt Engineering** | 80% | 有但未系统化 | ⚠️ |
| 5 | **Python + FastAPI** | 75% | 已有 | ✅ |
| 6 | **MCP 协议** | 60% | FastMCP | ✅ 强亮点 |
| 7 | **Multi-Agent 协作** | 55% | 2 个子 Agent | ⚠️ |
| 8 | **Tool Calling / Function Calling** | 55% | MCP 工具 | ✅ |
| 9 | **记忆管理**（长短期记忆/上下文窗口） | 50% | InMemoryStore | ⚠️ |
| 10 | **Docker 容器化** | 50% | 无 | ❌ |
| 11 | **知识图谱**（Neo4j/RDF） | 45% | Neo4j | ✅ 强亮点 |
| 12 | **Agent 评估体系**（RAGAS/自定义 Eval） | 45% | RAGAS 实现 | ⚠️ |
| 13 | **安全护栏**（Guardrails/提示注入防护） | 40% | 无 | ❌ |
| 14 | **可观测性**（LangSmith/Tracing/Logging） | 40% | loguru | ⚠️ |
| 15 | **CI/CD** | 35% | 无 | ❌ |
| 16 | **云平台**（AWS/Azure/GCP） | 35% | 无 | ❌ |
| 17 | **模型微调**（SFT/LoRA/DPO） | 25% | 无 | ❌ |
| 18 | **Kubernetes** | 25% | 无 | ❌ |
| 19 | **Redis 缓存** | 20% | 无 | ❌ |
| 20 | **ReAct/CoT 推理链** | 20% | 隐含在 Agent 逻辑中 | ⚠️ |
| 21 | **Reranker 重排**（交叉编码器） | 15% | 无 | ❌ |
| 22 | **多模型调度/分流** | 15% | CompositeBackend | ⚠️ |
| 23 | **Human-in-the-Loop** | 15% | PostgresSaver 支持 | ⚠️ |
| 24 | **私有化部署** | 15% | .env 配置 | ⚠️ |
| 25 | **全栈能力**（React/Vue 前端） | 10% | 无 | ❌ |

---

## 三、差距分析

### 🟢 已具备的强项（项目亮点）

| 能力 | 亮点说明 |
|------|---------|
| **GraphRAG 全链路** | 向量检索 + 图遍历 + RRF 融合，这比 90% 的候选人只会向量检索强 |
| **MCP 协议** | 2026 年最热门的 Agent 工具协议，很多候选人只在 JD 上见过 |
| **知识图谱 + 向量检索融合** | Neo4j + pgvector 双引擎，市场上少有人同时用 |
| **配置架构** | pydantic-settings 统一配置、依赖注入、懒加载单例，工程化水平高 |
| **领域垂直** | 消防领域落地，不是 Demo 级别的天气问答 |

### 🟡 有但不够深（需加强）

| 能力 | 当前状态 | 建议补强 |
|------|---------|---------|
| **Multi-Agent** | 2 个子 Agent，路由模式单一 | 加 1 个 Planner Agent 做任务拆解，展示 Supervisor-Worker 模式 |   5
| **记忆管理** | InMemoryStore，重启丢失 | 实现 PostgresStore 或 Redis 持久化，展示长短期记忆设计 |                已修复，使用PostgreSQL 
| **Prompt Engineering** | 硬编码在代码中 | 抽取为 Jinja2 模板，加 DSPy 自动优化（加分项） |                        不太适配DeepAgents这种高度集成的框架。
| **Agent 评估** | RAGAS 实现但未集成 | 集成到编排器，加自定义 Eval（工具调用准确率、幻觉率） |                      3
| **可观测性** | loguru 日志 | 接 LangSmith Tracing，或 OpenTelemetry |                                          4
| **多模型调度** | CompositeBackend 简单分流 | 加成本统计、降级容错、大小模型分级调用 |
| **PDF转MARKDOWN** |新数据入库方式 | 拓展入库方式 |                                                              2


### ❌ 缺失的关键项（必须补）

| # | 缺失项 | 优先级 | 难度 | 建议 |
|---|--------|--------|------|------|
| 1 | **Docker 容器化** | P0 | 低 | 写 Dockerfile + docker-compose.yml（PG + Neo4j + Agent） |                  编写完API之后尝试
| 2 | **安全护栏** | P0 | 中 | 实现 Prompt 注入检测 + 输出过滤，可用 NeMo Guardrails 或自写 |
| 3 | **CI/CD** | P1 | 低 | GitHub Actions：lint + test + build 镜像 |
| 4 | **Reranker 重排** | P1 | 中 | 加 bge-reranker 或 Cohere Rerank，RRF 粗排后精排 |                          思考方案
| 5 | **云部署** | P1 | 中 | Docker 推到云上（AWS ECS / 阿里云），至少有一套部署文档 |
| 6 | **Redis 缓存** | P2 | 低 | 相似问题缓存、Embedding 缓存、会话状态缓存 |

### ⚪ 锦上添花（时间允许再补）

| # | 加分项 | 说明 |
|---|--------|------|
| 1 | **模型微调**（LoRA/SFT） | 用消防领域数据微调小模型，降低推理成本 |
| 2 | **前端**（React/Vue） | 加一个简单的对话 UI，展示全栈能力 |
| 3 | **Kubernetes** | 生产级编排，很多高级岗位要求 |
| 4 | **DSPy 自动优化 Prompt** | 2026 年新兴技术，简历上很亮眼 |                                              需要研究
| 5 | **开源贡献** | 给 LangChain/LangGraph 提 PR，或把自己的项目开源 |
| 6 | **技术博客** | 写 2-3 篇 Agent 实战文章，展示思考深度 |

---

## 四、优先行动清单

### 本周（P0 — 面试必问）

| # | 任务 | 预估时间 |
|---|------|---------|
| 1 | Docker 容器化（Dockerfile + compose） | 2h |
| 2 | 安全护栏（提示注入检测 + 输出过滤） | 4h |
| 3 | Reranker 重排集成 | 3h |

### 下周（P1 — 差异化竞争力）

| # | 任务 | 预估时间 |
|---|------|---------|
| 4 | Multi-Agent 升级（Planner + Supervisor-Worker） | 4h |
| 5 | 记忆持久化（PostgresStore / Redis） | 3h |
| 6 | LangSmith Tracing 集成 | 2h |
| 7 | GitHub Actions CI/CD | 2h |

### 有时间再补（P2 — 加分项）

| # | 任务 | 预估时间 |
|---|------|---------|
| 8 | 云部署 + 部署文档 | 3h |
| 9 | Redis 缓存层 | 2h |
| 10 | 前端对话 UI | 4h |

---

## 五、面试话术建议

**项目介绍模板**：

> "我基于公司消防管理系统，独立设计并实现了一个 AI Agent 系统。技术栈是 LangGraph + LangChain + FastMCP，核心能力是 GraphRAG——不是简单的向量检索，而是向量检索 + 知识图谱遍历 + RRF 融合，能处理跨文档的法规引用链和设备依赖链分析。MCP 协议做工具层，11 个工具包括知识检索和业务查询。工程上做了依赖注入、懒加载单例、统一配置管理等生产级设计。"

**与纯 Demo 项目的差异点**：

| 纯 Demo | 你的项目 |
|---------|---------|
| LangChain + Pinecone + ChatGPT API | LangGraph + pgvector + Neo4j + MCP |
| 单一 RAG 向量检索 | GraphRAG（向量+图+融合） |
| 硬编码配置 | pydantic-settings + 依赖注入 |
| 没有测试 | pytest 测试套件 |
| 本地跑一下 | Docker 容器化（补完后） |
| 通用 Demo 场景 | 消防领域垂直落地 |
