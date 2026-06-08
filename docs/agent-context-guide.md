# Agent 上下文与运行时指南

> 本文档解释 DeepAgents 框架中 `state` 与 `runtime` 的区别、作用及使用场景。

---

## 一、核心概念

在 Agent 中间件（Middleware）中，有两个关键参数贯穿整个生命周期：

| 参数 | 类型 | 本质 | 类比 |
|:---|:---|:---|:---|
| `state` | `AgentState` | 对话状态（数据） | 游戏的**存档文件** |
| `runtime` | `Any` / 运行时容器 | 运行时环境（基础设施） | 游戏的**引擎系统** |

---

## 二、state —— 对话的"记忆"

### 2.1 包含内容

- **消息历史** (`messages`): 用户与 AI 的对话记录
- **中间结果**: Agent 的思考过程、工具调用结果
- **当前步骤**: 当前执行到哪个阶段

### 2.2 代码示例

```python
async def aafter_agent(self, state, runtime):
    # 从 state 中获取对话内容
    messages = getattr(state, "messages", [])
    
    # 遍历消息，找到最后一条用户消息
    for msg in reversed(messages):
        if getattr(msg, "type", None) == "human":
            user_message = msg.content
            break
```

### 2.3 特点

- **动态变化**: 每轮对话都会更新
- **会话隔离**: 不同对话有不同的 state
- **自动压缩**: 消息过长时框架会自动摘要

---

## 三、runtime —— 运行的"工具箱"

### 3.1 包含内容

| 属性 | 用途 | 示例 |
|:---|:---|:---|
| `runtime.context` | 用户上下文信息 | `user_id`, `username` |
| `runtime.store` | 持久化存储后端 | 文件读写、数据库操作 |
| `runtime.model` | LLM 模型实例 | 用于额外调用 |

### 3.2 代码示例

```python
async def aafter_agent(self, state, runtime):
    # 从 runtime 获取用户信息
    ctx = getattr(runtime, "context", {})
    user_id = ctx.get("user_id")
    
    # 从 runtime 获取存储后端
    store = getattr(runtime, "store", None)
    
    # 使用 store 保存数据
    store.write_file(f"/memories/{user_id}/preferences.md", content)
```

### 3.3 特点

- **全局共享**: 同一应用实例内共享
- **基础设施**: 提供存储、模型等能力
- **跨对话持久**: store 中的数据可跨对话保留

---

## 四、上下文层级对照表

根据框架设计，上下文分为五个层级：

| 上下文层级 | 对应参数 | 内容 | 生命周期 |
|:---|:---|:---|:---|
| **输入上下文** | `state`（初始化时） | 系统提示、技能文件、记忆文件 | 静态加载，每次 invoke 生效 |
| **运行时上下文** | `runtime` | 用户元数据、API 密钥、数据库连接 | 单次调用级别，可传播给子 Agent |
| **上下文压缩** | `state`（内部处理） | 自动卸载大块内容、对话摘要 | 自动触发，保证不超出窗口 |
| **上下文隔离** | 子 Agent 的独立 `state'` + `runtime'` | 子 Agent 独立运行，仅返回结果 | 每个子 Agent 拥有独立上下文 |
| **长期记忆** | `runtime.store` | 跨对话的持久化文件存储 | 可跨线程/用户/组织持续存在 |

---

## 五、形象比喻

```
对话流程 = 学生(state) 在 教室(runtime) 里上课

state（学生）：
  - 记住了什么（messages）
  - 当前在做什么（当前步骤）
  - 作业写到哪里了（中间结果）

runtime（教室）：
  - 学生身份信息（context.user_id）
  - 储物柜（store）
  - 黑板/投影仪（model、tools）
```

---

## 六、使用建议

| 你想操作什么 | 使用哪个参数 |
|:---|:---|
| 读取/修改对话内容、消息历史 | `state` |
| 获取用户信息、存取文件、使用基础设施 | `runtime` |
| 保存跨对话的数据 | `runtime.store` |
| 控制对话长度、摘要 | 框架自动处理 `state` |

---

## 七、完整示例

```python
from langchain.agents.middleware import AgentMiddleware

class MyMiddleware(AgentMiddleware):
    async def aafter_agent(self, state, runtime):
        # ===== 从 state 获取对话内容 =====
        messages = getattr(state, "messages", [])
        
        # ===== 从 runtime 获取用户信息 =====
        ctx = getattr(runtime, "context", {})
        user_id = ctx.get("user_id")
        
        # ===== 从 runtime 获取存储能力 =====
        store = getattr(runtime, "store", None)
        
        # 处理逻辑...
        
        # 保存到长期记忆
        if store and user_id:
            store.write_file(
                f"/memories/{user_id}/history.md",
                "用户对话记录..."
            )
```

---

## 八、相关文件

- `src/agent/middlewares/memory_update.py` —— 记忆更新中间件
- `src/agent/middlewares/context_injection.py` —— 上下文注入中间件

---

> 如有疑问，请查看具体中间件实现或咨询框架文档。
