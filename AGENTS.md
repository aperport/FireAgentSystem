 # 仓库贡献指南

 本文档为 FireAgentSystem 仓库提供实用的贡献指引。

 ## 项目结构与模块组织

 代码库的组织结构如下：

 - `src/agent/` — 核心智能体框架：主智能体、子智能体、中间件、记忆模块和工具集成。
 - `src/graph_rag/` — GraphRAG 模块：数据摄入、实体抽取、图遍历、向量检索和评估。
 - `src/mcp_server/` — MCP 服务器实现及消防领域自定义工具。
 - `src/test/` — 测试套件（pytest）。
 - `src/util_tools/` — 共享工具模块（日志等）。
 - `data/` — 运行时数据文件（如 JSON 导出）。
 - `docs/` — 项目文档（如法律法规参考）。

 ## 构建、测试与开发命令

 安装依赖并运行项目：

 ```bash
 pip install -r requirements.txt
 python run.py --mode agent        # 启动智能助手对话（CLI）
 python run.py --mode mcp-server   # 启动 FastMCP 工具服务
 ```

 运行完整测试套件：

 ```bash
 pytest src/test/ -v --tb=long
 ```

 ## 代码风格与命名规范

 - **语言**：Python 3.13+；在合适的地方使用类型提示。
 - **缩进**：4 个空格。
 - **命名**：函数和变量使用 `snake_case`；类使用 `PascalCase`；常量使用 `UPPER_CASE`。
 - **文档字符串**：模块级文档字符串使用中文（项目约定），函数文档字符串保持简洁。
 - **导入**：按标准库、第三方库、本地模块分组导入；使用绝对导入。
 - **配置**：将密钥和环境相关值保存在 `.env` 中（参考 `.env` 模板）；切勿提交到版本库。

 ## 测试规范

 - **框架**：pytest，支持异步测试（`pytest-asyncio`）。
 - **Fixtures**：共享 fixtures 定义在 `src/test/conftest.py` 中（如 `mock_runtime`、`mock_store`）。
 - **覆盖率**：在智能体逻辑、MCP 工具、中间件和 GraphRAG 流水线等模块上争取有意义的覆盖。
 - **运行测试**：
   ```bash
   pytest src/test/ -v
   pytest src/test/test_mcp_tools.py -v
   ```

 ## 提交与合并请求规范

 - **提交信息**：遵循历史中的约定式提交风格：`feat:`、`fix:`、`docs:`、`refactor:`。
   示例：`feat(graph_rag): add async pipeline for entity deduplication`
 - **合并请求**：提供清晰的描述，关联相关议题，并在适当时附上测试结果或截图。
 - **作用域标签**：使用模块前缀（如 `graph_rag`、`agent`、`evaluator`）以保持提交历史清晰可读。

 ## 安全与配置提示

 - 切勿提交 `.env` 文件；它们已通过 `.gitignore` 忽略。
 - 项目使用 Neo4j、PostgreSQL/pgvector 和 MongoDB；在启动依赖这些服务的功能前，确保本地服务已运行。
 - 定期检查 `requirements.txt` 中的依赖更新和安全补丁。

 ## 架构概览

 FireAgentSystem 是基于 LangGraph 构建的消防安全智能助手。它结合了：
 - **智能体编排**（LangGraph/LangChain）：支持多轮对话和子智能体委派。
 - **GraphRAG**（Neo4j + pgvector）：用于知识摄入、实体/关系抽取和混合检索。
 - **MCP 服务器**（FastMCP）：暴露消防领域的工具接口。

 新功能应遵守模块边界：摄入逻辑放在 `graph_rag/ingestion/`，智能体逻辑放在 `agent/`，工具通过 `mcp_server/` 暴露。
