# FireAgentSystem 项目记忆

## 项目概况
- 消防安全智能助手，基于 LangGraph/LangChain + GraphRAG(Neo4j+pgvector) + MCP Server(FastMCP)
- Python 3.13+，使用 DeepAgents 框架

## 2026-07-28 过度设计审查与重构

### 已完成的修改
1. **删除死代码**：orchestrator.py 的 `main()` + `GraphQuery`/`VectorQuery` 类、save_data.py 的 `main()`、server_main.py 的 `main()`
2. **删除未使用的关系 dataclass**：schema.py 中 11 个关系类（ContainsFunctionRel 等），writer.py 不使用它们
3. **合并重复逻辑**：db_operator.py 的 `insert_chunks`/`insert_picture` 提取为 `_insert_documents()` 公共方法
4. **统一异常处理**：main_agent.py 的 5 处重复 try/except 统一为 `_step()` 辅助函数
5. **修复并发控制**：orchestrator.py 的 `_BM25Index` 布尔锁改为 `threading.Lock`（双重检查锁定模式）
6. **简化 logger**：util_tools/logger.py 从手动 logging 配置改为代理 loguru，保持 `get_logger(name)` 接口不变
7. **简化单例**：collections.py 的 `PGVectorManager.__new__` 单例改为模块级 `_pg_instance` + `get_pg_instance()` 函数
8. **修复 ingestion/__init__.py**：添加实际导出（原先只有文档字符串）
9. **更新 knowledge_tools.py**：将 `VectorQuery`/`GraphQuery` 引用替换为底层组件直接调用

### 接口变更
- `PGVectorManager(...)` → `get_pg_instance(...)`（db_operator.py, orchestrator.py 已更新）
- `from util_tools.logger import get_logger` 接口不变，内部实现改为 loguru
- `knowledge_tools.py` 不再导入 `VectorQuery`/`GraphQuery`，改为直接使用 `VectorRetriever`/`GraphTraverser`

### 未处理的低优先级项
- `aiofiles` 可用 `asyncio.to_thread` 替代（需确认所有调用方）
- `db_retriever.py` 的自定义中文停用词表可用 jieba 自带的
- 评估模块（evaluator.py, retrieval_evaluator.py）未接入 orchestrator，建议移至 test/
- requirements.txt 中 fastapi/uvicorn 对应的 api_view/ 目录为空

## 记忆系统架构要点（2026-09-11 走读，详见当日日志）

- 记忆读写模式：**写**靠 `MemoryUpdateMiddleware`（`aafter_agent`）自动提取实体写 StoreBackend；**读**靠 `ContextInjectionMiddleware` 注入提示、Agent 自己 `read_file`。无显式加载函数。
- `/memories/` 由 `main_agent.py` 的 CompositeBackend 路由到 StoreBackend（namespace=user_id），底层 PostgresStore。
- `_merge_preferences` 滚动窗口：equipment 10 / zones 5 / queries 5，不会无限叠加。

### 用户待优化项（memory_update.py，用户自行处理）
1. `preferred_*` 偏好字段仅存在于 `AGENTS.md` 和死代码 `UserPreferences`，提取器不提取、提示词不驱动 → 文件实为"近期活动记录"而非"偏好文件"
2. `AGENTS.md` 偏好文件示例缺 `recent_zones` 区块，与实际写入格式不符
3. `_extract_entities` 手动 `find("{")` 抠 JSON，与文件头"使用 with_structured_output"注释不符
4. 每次 `aafter_agent` 重新实例化 `MemoryUpdateMiddlewareTools`（可移到 `__init__`）
5. 业务关键词/跳过词表硬编码在类里
