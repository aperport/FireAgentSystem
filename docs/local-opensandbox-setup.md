# 本地 OpenSandbox 沙箱部署方案

> 参考：[OpenSandbox 实战指南](https://www.cnblogs.com/linlf03/p/20195972)
>
> 目标：将远程 OpenSandbox API 替换为本地部署的 OpenSandbox 服务，消除对外部 API Key 的依赖。

---

## 一、现状分析

当前系统使用 **OpenSandbox 云服务**（`api.opensandbox.io`），需要：
- `OPENSANDBOX_API_KEY` — 付费或申请
- 网络连接到远程服务器

**问题**：
- 需要外部 API Key，增加配置复杂度
- 依赖网络稳定性
- 存在数据隐私顾虑

---

## 二、本地 OpenSandbox 架构

```
┌─────────────────────────────────────────────┐
│              FireAgentSystem                 │
│  ┌─────────────────────────────────────┐   │
│  │         Agent 主流程                 │   │
│  │   ┌─────────────┐  ┌─────────────┐ │   │
│  │   │ 主 Agent    │→│ setup_sandbox│ │   │
│  │   └─────────────┘  └──────┬──────┘ │   │
│  └───────────────────────────┼────────┘   │
│                              │              │
│  ┌───────────────────────────▼────────┐   │
│  │   OpenSandbox Python SDK (本地)     │   │
│  │   opensandbox + code-interpreter   │   │
│  └───────────────────────────┬────────┘   │
│                              │              │
│  ┌───────────────────────────▼────────┐   │
│  │   OpenSandbox Server (本地:8080)   │   │
│  │   opensandbox-server               │   │
│  └───────────────────────────┬────────┘   │
│                              │              │
│  ┌───────────────────────────▼────────┐   │
│  │   Docker Container (本地隔离)      │   │
│  │   code-interpreter:v1.0.2          │   │
│  └────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

---

## 三、部署步骤

### 3.1 环境准备

| 依赖 | 版本 | 说明 |
|------|------|------|
| Docker | ≥ 20.10 | 容器运行时 |
| Python | ≥ 3.10 | SDK 运行环境 |
| uv | latest | Python 包管理器 |

### 3.2 安装 OpenSandbox Server

```bash
# 安装 Server 端
uv pip install opensandbox-server

# 生成配置文件（Docker 运行时示例）
opensandbox-server init-config ~/.sandbox.toml --example docker
```

### 3.3 启动 Server

```bash
# 启动本地服务（默认 localhost:8080）
opensandbox-server
```

### 3.4 预拉取 Docker 镜像

```bash
# 国内镜像源（推荐）
docker pull sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2

# 验证
docker images | grep code-interpreter
```

### 3.5 安装 Python SDK

```bash
uv pip install opensandbox-code-interpreter
```

---

## 四、代码改造

### 4.1 修改 `sandbox_setup.py`

当前代码连接远程 OpenSandbox：

```python
# 当前：连接远程 OpenSandbox API
OPENSANDBOX_API_KEY = os.getenv("OPENSANDBOX_API_KEY", "")
OPENSANDBOX_DOMAIN = os.getenv("OPENSANDBOX_DOMAIN", "api.opensandbox.io")
```

改造为连接本地 Server：

```python
# 改造后：连接本地 OpenSandbox Server
OPENSANDBOX_DOMAIN = os.getenv("OPENSANDBOX_DOMAIN", "http://localhost:8080")
# 本地模式不需要 API Key
OPENSANDBOX_API_KEY = os.getenv("OPENSANDBOX_API_KEY", "local")
```

### 4.2 修改 `custom_opensandbox.py`

当前使用 `SandboxSync`（同步 SDK），需要改为异步 `Sandbox`：

```python
# 当前
from opensandbox import SandboxSync
from opensandbox.config import ConnectionConfigSync

# 改造后（本地 Server 使用异步 SDK）
from opensandbox import Sandbox
from opensandbox.config import ConnectionConfig
import httpx

# 配置本地连接
config = ConnectionConfig(
    domain="http://localhost:8080",
    use_server_proxy=False,
    request_timeout=timedelta(seconds=120),
    transport=httpx.AsyncHTTPTransport(limits=httpx.Limits(max_connections=20)),
)
```

### 4.3 创建沙箱逻辑改造

```python
async def setup_local_sandbox():
    """创建本地 OpenSandbox 沙箱"""
    
    sandbox = await Sandbox.create(
        "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2",
        entrypoint=["/opt/opensandbox/code-interpreter.sh"],
        env={"PYTHON_VERSION": "3.11"},
        timeout=timedelta(hours=2),
        connection_config=config,
        ready_timeout=timedelta(seconds=120),
        health_check_polling_interval=timedelta(seconds=5),
    )
    
    return sandbox
```

---

## 五、完整示例

```python
import asyncio
import httpx
from datetime import timedelta
from opensandbox import Sandbox
from opensandbox.config import ConnectionConfig

async def main():
    # 1. 配置本地连接
    config = ConnectionConfig(
        domain="http://localhost:8080",
        use_server_proxy=False,
        request_timeout=timedelta(seconds=120),
        transport=httpx.AsyncHTTPTransport(limits=httpx.Limits(max_connections=20)),
    )
    
    # 2. 创建沙箱
    sandbox = await Sandbox.create(
        "sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2",
        entrypoint=["/opt/opensandbox/code-interpreter.sh"],
        env={"PYTHON_VERSION": "3.11"},
        timeout=timedelta(hours=2),
        connection_config=config,
        ready_timeout=timedelta(seconds=120),
    )
    
    print(f"沙箱创建成功: {sandbox.id}")
    
    # 3. 使用沙箱
    async with sandbox:
        # 执行命令
        execution = await sandbox.commands.run("echo 'Hello Local OpenSandbox!'")
        print(execution.logs.stdout[0].text)
        
        # 写入文件
        await sandbox.files.write_files([
            WriteEntry(path="/tmp/test.txt", data="Hello World", mode=644)
        ])
        
        # 读取文件
        content = await sandbox.files.read_file("/tmp/test.txt")
        print(f"Content: {content}")
    
    # 4. 清理
    await sandbox.kill()

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 六、与现有代码集成

### 6.1 修改 `main_agent.py` 的沙箱初始化

```python
# 当前
from agent.backends.sandbox_setup import setup_sandbox
sandbox_backend = setup_sandbox(config=sandbox_config, sandbox_id=sandbox_id)

# 改造后（增加本地模式回退）
async def setup_sandbox_with_fallback(config=None, sandbox_id=None):
    """优先使用本地 OpenSandbox，失败则回退到远程"""
    try:
        # 尝试本地模式
        return await setup_local_sandbox(config)
    except Exception:
        logger.warning("本地 OpenSandbox 不可用，回退到远程模式")
        # 回退到远程
        return setup_sandbox(config=config, sandbox_id=sandbox_id)
```

### 6.2 环境变量配置

```bash
# .env 文件
# 本地模式
OPENSANDBOX_DOMAIN=http://localhost:8080
OPENSANDBOX_API_KEY=local

# 远程模式（备用）
# OPENSANDBOX_DOMAIN=api.opensandbox.io
# OPENSANDBOX_API_KEY=your_api_key
```

---

## 七、常见问题

### 7.1 沙箱创建超时

**原因**：首次拉取 Docker 镜像耗时较长

**解决**：
```bash
# 预拉取镜像
docker pull sandbox-registry.cn-zhangjiakou.cr.aliyuncs.com/opensandbox/code-interpreter:v1.0.2
```

### 7.2 健康检查超时

**原因**：`use_server_proxy=True` 但本地 Server 不支持

**解决**：
```python
config = ConnectionConfig(
    domain="http://localhost:8080",
    use_server_proxy=False,  # 禁用 server proxy
    # ...
)
```

### 7.3 API 路径 404

**原因**：SDK 版本与 Server 版本不匹配

**解决**：
1. 确认 Server 版本：`opensandbox-server --version`
2. 安装匹配的 SDK 版本
3. 查看 OpenAPI 文档：`http://localhost:8080/docs`

---

## 八、优势对比

| 特性 | 远程 OpenSandbox | 本地 OpenSandbox |
|------|------------------|------------------|
| API Key | 需要 | 不需要（或 dummy） |
| 网络依赖 | 需要外网 | 仅本地 localhost |
| 数据隐私 | 数据出本地 | 完全本地隔离 |
| 成本 | 按量计费 | 免费（仅 Docker） |
| 部署复杂度 | 低 | 中等（需 Docker） |
| 适用场景 | 生产环境 | 开发/测试环境 |

---

## 九、待实现

- [ ] 修改 `sandbox_setup.py` 支持本地模式
- [ ] 修改 `custom_opensandbox.py` 使用异步 SDK
- [ ] 添加本地/远程模式自动切换
- [ ] 编写本地部署脚本（`setup_local_sandbox.sh`）
- [ ] 更新 `AGENTS.md` 文档
