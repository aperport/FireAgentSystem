---
name: sandbox-audit-20260714
description: 沙箱实现代码审计报告（2026-07-14）
metadata:
  type: project
---

# 沙箱实现代码审计报告 — 2026-07-14

基于 `feature/dev` 分支对沙箱相关实现进行专项审计，共发现 **10 个问题**。

> 审计范围：`custom_opensandbox.py`、`sandbox_setup.py`、`main_agent.py`、`config.py`

---

## 🔴 Critical — 运行必崩（2 个）

| # | 状态 | 文件 | 行 | 问题 | 说明 | 修复建议 |
|---|------|------|----|------|------|---------|
| 1 | ❌ | `config.py` | 79-80 | `PostgresSaver` 在 `with` 块内实例化，退出后连接关闭 | 模块导入时执行 `with PostgresSaver(...) as CHECKPOINT`，退出时连接关闭，但 `CHECKPOINT` 被后续代码引用，使用时必崩 | 改为全局保持连接：`CHECKPOINT = PostgresSaver.from_conn_string(...)`，在应用退出时手动关闭 |
| 2 | ❌ | `sandbox_setup.py` | 49-51 | `config` 参数类型为 `dict` 但使用 `getattr` | `setup_sandbox(config=sandbox_config, ...)` 中 `config` 传入的是 `dict`，但代码用 `getattr(config, "api_key", None)`，字典没有属性访问，返回 `None`，回退到环境变量 | 明确 `config` 类型：如果是 `dict` 改用 `config.get("api_key")`；如果是对象则保留 `getattr` |

---

## 🟠 High — 功能缺陷 / 潜在风险（4 个）

| # | 状态 | 文件 | 行 | 问题 | 说明 | 修复建议 |
|---|------|------|----|------|------|---------|
| 3 | ❌ | `custom_opensandbox.py` | 74 | `export PATH` 拼接命令注入风险 | `full_command = f'export PATH="..." && {command}'` 中，如果 `command` 包含 `&`、`|`、`;` 等特殊字符，会导致命令解析错误或注入 | 检查 SDK 是否支持 `env` 参数传递环境变量；如不支持，对 `command` 进行转义处理 |
| 4 | ❌ | `sandbox_setup.py` | 111-113 | 虚拟环境重复创建 | 每次 `setup_sandbox()` 都执行 `python3 -m venv /opt/skills-venv`，venv 已存在时会报错 | 先检查目录是否存在：`test -d /opt/skills-venv`，不存在再创建 |
| 5 | ❌ | `sandbox_setup.py` | 150-157 | 文件存在性检查 N 次网络往返 | 逐个文件 `test -f` 检查远程存在性，N 个文件 = N 次远程调用，性能极差 | 使用 `find` 或 `ls` 一次列出所有远程文件，批量对比；或改用 `rsync` 同步 |
| 6 | ❌ | `main_agent.py` | 86-89 | 异常处理丢失原始堆栈 | `except Exception as e: raise RuntimeError("...")` 丢失了原始异常链 | 使用 `raise RuntimeError("...") from e` 保留异常链 |

---

## 🟡 Medium — 设计缺陷 / 潜在问题（3 个）

| # | 状态 | 文件 | 行 | 问题 | 说明 | 修复建议 |
|---|------|------|----|------|------|---------|
| 7 | ❌ | `main_agent.py` | 98-112, 182 | `backend()` 闭包被多次调用 | `backend()` 在 `create_main_agent` 中被调用两次（第 147 行和 182 行），每次都创建新的 `CompositeBackend` 实例，但底层共享同一个 `sandbox_backend` | 在 `create_main_agent` 内只创建一次 `CompositeBackend` 实例，多处复用 |
| 8 | ❌ | `main_agent.py` | 235-246 | `_AgentProxy` 无锁，多线程竞态 | `_ensure_initialized()` 中 `if self._agent is not None` 检查和赋值之间没有锁，多线程环境下可能重复初始化 | 添加 `threading.Lock()` 保护初始化逻辑 |
| 9 | ❌ | `custom_opensandbox.py` | 118-119 | `download_files` 编码假设 | 假设所有文本都是 UTF-8，但沙箱中的文件可能是其他编码（如 GBK） | 尝试 UTF-8 解码，失败时回退到 `latin-1` 或根据文件头检测编码 |

---

## 🔵 Low — 代码风格 / 优化建议（1 个）

| # | 状态 | 文件 | 行 | 问题 | 说明 | 修复建议 |
|---|------|------|----|------|------|---------|
| 10 | ❌ | `main_agent.py` | 291-300 | `start_main_agent` 缺少错误处理 | `ainvoke` 调用未包裹 try/except，失败时抛出未处理异常 | 添加 try/except 包裹 `ainvoke`，返回友好的错误信息 |

---

## 修复统计

| 级别 | 总数 | ✅ 已修复 | ❌ 未修复 | 修复率 |
|------|------|-----------|-----------|--------|
| 🔴 Critical | 2 | 0 | 2 | 0% |
| 🟠 High | 4 | 0 | 4 | 0% |
| 🟡 Medium | 3 | 0 | 3 | 0% |
| 🔵 Low | 1 | 0 | 1 | 0% |
| **合计** | **10** | **0** | **10** | **0%** |

---

## 修复优先级建议

1. **🔴 Critical 1-2**：不修项目完全跑不起来
   - #1 `config.py` 的 `PostgresSaver` 连接问题会导致所有用到 `CHECKPOINT` 的地方崩溃
   - #2 `sandbox_setup.py` 的 `config` 参数类型问题会导致沙箱初始化失败

2. **🟠 High 3-6**：功能缺陷和性能问题
   - #3 命令注入风险需要优先处理
   - #5 文件上传性能问题在 skills 文件多时会严重影响启动速度

3. **🟡 Medium 7-9**：设计缺陷
   - #7 `backend()` 重复创建实例是设计问题，建议重构
   - #8 多线程竞态在高并发场景下会暴露

4. **🔵 Low 10**：优化建议
   - #10 错误处理完善用户体验

---

## 关联文档

- [[bug-audit-20260712]] — 全量代码审计报告（2026-07-12）
