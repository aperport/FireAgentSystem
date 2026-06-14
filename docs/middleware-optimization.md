# 中间件优化方案

> 基于当前 5 个中间件的代码审查，按优先级排列

---

## 一、P0 — 架构级改造

### 1. 偏好存储：文件 → 数据库

**现状**：`memory_update.py` 将用户偏好写入 `/memories/{user_id}/preferences.md`，手动解析 Markdown 行、正则匹配 `recent_suppliers:` / `recent_queries:` 区块，脆弱且不可扩展。

**方案**：

| 存储类型 | 适用场景 | 推荐选型 |
|---------|---------|---------|
| 关系型 DB | 结构化偏好（供应商列表、查询历史、用户设置） | **PostgreSQL**（项目已有 MongoDB，也可复用） |
| 向量 DB | 语义检索偏好（"这个用户之前问过类似问题吗"） | **Milvus / Chroma** |
| 图 DB | 供应商-零件-订单关系网络 | Neo4j（远期考虑） |

**改造要点**：
- `UserPreferences` 已是 `@dataclass`，直接映射为 DB 表/文档
- `memory_update.py` 的 `_merge_preferences()` 60 行 Markdown 解析 → 替换为一条 `UPSERT` SQL
- `context_injection.py` 的 `read_file /memories/{user_id}/preferences.md` → 替换为 DB 查询
- 向量 DB 存储 query embedding，支持"相似需求推荐"

### 2. StoreBackend：InMemoryStore → 持久化

**现状**：`config.py` 中 `STORE = InMemoryStore()`，重启即丢失。

**方案**：LangGraph 原生支持 `PostgresStore` / `MongoDBStore`，一行替换：
```python
# before
STORE = InMemoryStore()
# after
from langgraph.store.postgres import PostgresStore
STORE = PostgresStore(conn_string=POSTGRES_URI)
```

---

## 二、P1 — 逻辑优化

### 3. 关键词提取：硬编码 → LLM 驱动 + 可配置

**现状**：`MemoryUpdateMiddlewareTools` 硬编码 26 个 `business_keywords` 和 12 个 `skip_words`。

**方案**：
- 关键词列表移至 `config.yaml` 或 DB 配置表，支持热更新
- 短期：保留关键词快速过滤作为**前置筛子**，减少 LLM 调用
- 长期：用 embedding 相似度替代关键词匹配，自动识别业务相关消息

### 4. 实体提取：Prompt 注入 → 结构化输出

**现状**：`_extract_entities()` 用字符串拼接 prompt，手动 `json.loads(text[start:end+1])` 解析，脆弱。

**方案**：
```python
# 使用 with_structured_output 替代手动 JSON 解析
from pydantic import BaseModel

class ExtractedEntities(BaseModel):
    suppliers: list[str] = []
    query: str = ""

structured_model = model.with_structured_output(ExtractedEntities)
result = await structured_model.ainvoke(prompt)
```

### 5. ContextInjection：硬编码提示 → 模板化

**现状**：`notice` 字符串硬编码在代码中，包含文件路径 `/memories/{user_id}/preferences.md`。

**方案**：
- 提示模板移至 `prompts.py` 或 Jinja2 模板文件
- 偏好数据直接从 DB 查询后注入，而非让 Agent 再 `read_file`

---

## 三、P2 — 工程质量

### 6. SkillsSync：同步阻塞 → 异步批处理

**现状**：`_sync_files()` 是同步方法，逐文件 `upload_files()`，在 `abefore_agent` 中用 `run_in_executor` 包装。

**方案**：
- 收集所有待上传文件后，一次 `upload_files(batch)` 批量上传
- 哈希缓存加 TTL，避免内存无限增长
- 考虑用 `watchdog` 监听本地变更，而非每次 Agent 调用都全量扫描

### 7. UserSkillsRestore：空实现 → 补全或移除

**现状**：文件只有 docstring，无实现代码。

**方案**：补全实现或删除空文件，避免误导。

### 8. 统一日志与指标

**现状**：各中间件日志格式不统一，无性能指标。

**方案**：
- 统一结构化日志格式：`{middleware, user_id, action, duration_ms, result}`
- 关键路径加 `time.perf_counter()` 计时
- 接入 Prometheus / OpenTelemetry 采集中间件延迟

### 9. 中间件配置外部化

**现状**：阈值（摘要 85%、ModelCallLimit 50/200）硬编码。

**方案**：统一到 `config.yaml`：
```yaml
middlewares:
  summarization:
    threshold: 0.85
  model_call_limit: 50
  tool_call_limit: 200
  memory_update:
    max_suppliers: 10
    max_queries: 5
```

---

## 改造路线图

```
Phase 1（1-2周）: #2 Store持久化 + #4 结构化输出 + #5 模板化
Phase 2（2-3周）: #1 偏好DB迁移 + #3 关键词可配置
Phase 3（持续）:  #6-#9 工程质量提升
```
