"""
消防后勤智能助手 — 主Agent入口模块。

使用 DeepAgents 框架创建主 Agent 协调器，采用 async graph factory 模式。
主 Agent 负责意图判断和子 Agent 委派：
    - 知识咨询类问题 → fire-qa-assistant（GraphRAG问答）
    - 数据管理类问题 → fire-management-analyst（报表评鉴）

初始化流程（9步）：
    1. 创建沙箱 → 2. 上传AGENTS.md → 3. CompositeBackend分流
    → 4. MCP工具加载 → 5. 工具池构建 → 6. 子Agent YAML加载+工具解析
    → 7. 子Agent中间件注入 → 8. 主Agent中间件链组装 → 9. create_deep_agent()

对外接口：
    get_agent()         — 同步获取Agent实例（懒加载）
    get_agent_async()   — 异步获取Agent实例（适用于FastAPI等异步环境）
"""


import asyncio
import logging
import os
import sys
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StoreBackend
from langchain_core.runnables import RunnableConfig
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)
from agent.schema import FireLogisticsContext
from agent.memory.prompts import system_prompt
from agent.backends.sandbox_setup import setup_sandbox
from agent.config import CHECKPOINT, LOCAL_AGENTS_MD, SKILLS_STORE_NAMESPACE, STORE, SUMMARY_MODEL
from agent.middleware_config import create_analyst_middleware
from agent.middlewares.context_injection import ContextInjectionMiddleware
from agent.middlewares.memory_update import MemoryUpdateMiddleware
from agent.subagents.read_yaml import assemble_subagent
from agent.tools.MCP_client import load_mcp_tools

def _setup_logging() -> None:
    """配置日志：开发环境输出到控制台，生产环境输出到文件。"""
    env = os.environ.get("APP_ENV", "development")
    if env == "production":
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            filename="erp_agent.log",
            filemode="a",
        )
    else:
        logging.basicConfig(
            level=logging.ERROR,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            stream=sys.stdout,
        )

_setup_logging()
logger = logging.getLogger(__name__)


async def create_main_agent(
        config: RunnableConfig | None = None,
        *,
        sandbox_id: str | None = None,
):
    """
    创建Agent智能助手，每次调用执行完整过程个过程
    1. 创建一个新的沙箱-> 1.2. 将Agent写入沙箱 ->1.3 CompositeBackend 分流
    2. MCP工具加载
    3. 可视化工具合并 （一个网上链接的MCP工具，因为描述过多，需要进行合并，可选，也是大工具一种解体思路）
    4. 工具池构建 
    5. 子Agent的YAML文件加载 
    6. 创建子Agent中间件
    7. 工具名称解析
    8. 主Agent中间件
    9. 创建Agent

    arg:
        config: LangGraph RunnableConfig，由 langgraph 平台注入。 
            核心配置类：
            传递运行时上下文 - 如用户ID、会话ID等
            控制递归深度 - 防止 Agent 无限循环调用工具
            配置回调 - 用于日志记录、监控、调试
            条件分支 - 根据配置参数决定图的不同执行路径
        sandbox_id: 沙箱ID
    """

    logger.info("创建主Agent")
    try:
        sandbox_backend =  setup_sandbox(config=config, sandbox_id=sandbox_id)
    except Exception as e:
        logger.error(f"创建主Agent失败，原因：{e}")
        raise RuntimeError("因沙箱配置失败，无法构建智能体")
    
    # 上传Agent.md到沙箱
    logger.info("正在上传Agent.md到沙箱")
    ag_md_content = LOCAL_AGENTS_MD.read_text()
    sandbox_backend.upload_files([("Agent.md", ag_md_content.encode("utf-8"))])
    logger.info("上传Agent.md到沙箱成功")
    logger.info("主Agent创建完成，开始进行分流")

    def backend():
        """根据文件路径前缀将读写请求路由到不同的存储后端"""
        return CompositeBackend(
            default=sandbox_backend,                    # 默认：沙箱文件系统
            routes={
                "/memories/": StoreBackend(
                    # runtime=rt,                       # 该参数已废弃，无需传入
                    namespace=lambda r: (getattr(r.context, 'user_id', 'TEST'),),    # 用户偏好持久化 ，从上下文（类）中取出user_id，取不到用TEST    字典:dict.get(key, default)
                ),
                # "/persisted-skills/": StoreBackend(
                #     runtime=rt,
                #     namespace=lambda r: SKILLS_STORE_NAMESPACE,
                # ),
            },
        )

    # MCP工具加载
    logger.info("开始加载MCP工具")
    try:
        all_mcp_tools = await load_mcp_tools()
        logger.info("MCP工具加载完成")
    except Exception as e:
        logger.error(f"MCP工具加载失败，原因：{e}")
        raise RuntimeError("因MCP工具加载失败，无法构建智能体")
    
    # 创建技能管理工具 

    
    # 工具池构建
    logger.info("开始构建工具池")

    available_tools = list(all_mcp_tools.values())

    logger.info("工具池构建完成,共计{}个工具".format(len(available_tools)))

    # 子Agent的Yaml加载（assemble_subagents 是异步函数，需要 await）
    logger.info("开始加载子Agent")
    try:
        subagents  = await assemble_subagent()
        if not subagents :
            logger.error("子Agent加载失败，原因：子Agent为空,将使用主智能体运行")
        logger.info("子Agent加载完成")
    except Exception as e:
        logger.error(f"子Agent加载失败，原因：{e}")
        raise RuntimeError("因子Agent加载失败，无法构建智能体")

    # 创建子Agent中间件,此处使用了子智能体，需根据实际业务设置
    # 子Agent中间件通过 subagent 配置的 middleware 字段传入
    logger.info("开始创建子Agent中间件")  
    analyst_middleware = create_analyst_middleware(SUMMARY_MODEL, backend)
    # 将中间件注入到对应子Agent配置中
    for subagent in subagents:
        if subagent.get("name") in ("fire-management-analyst", "analyst"):
            subagent["middleware"] = analyst_middleware

    

    # 主智能体中间件
    logger.info("开始创建主Agent中间件")
    from agent.middlewares.tools_summarization import build_summarization_middleware
    try:
        main_mid = [
            ContextInjectionMiddleware(),
            build_summarization_middleware(sandbox_backend, SUMMARY_MODEL),
            MemoryUpdateMiddleware(model=SUMMARY_MODEL),
            ModelCallLimitMiddleware(run_limit=50),    # 限制模型调用次数
            ToolCallLimitMiddleware(run_limit=200),    # 限制工具调用次数
        ]
    except Exception as e:
        logger.error(f"主Agent中间件创建失败，原因：{e}")
        raise RuntimeError("因主Agent中间件创建失败，无法构建智能体")
    logger.info("主Agent中间件创建完成")

    # 创建主Agent
    logger.info("开始创建主Agent")
    try:
        main_agent = create_deep_agent(
            model=SUMMARY_MODEL,
            system_prompt=system_prompt,
            # skills= ["/skills/main/"],            # 暂不使用skills
            memory=["/memories/"],                  # 用户记忆存储路径（偏好、历史等，由StoreBackend按user_id隔离），上传之后的路径
            tools=available_tools,                  # 工具，来源很多，可以是MCP工具（有三种传输方式），也可以是自定义工具
            subagents=subagents,                    # 子智能体，类型subagent类型，即字典，里面含有name、description、system_prompt、tool字段，存在校验；另一种是CompiledSubAgent，即langgraph的智能体组合。
            middleware=main_mid,                    # 中间件。
            backend=backend(),                      # 后端：指定数据存储、文件系统、或者记忆（Memory）持久化的具体底层实现，存在几个默认实现，目前使用自定义OpenSandBox。
            store=STORE,                            # 长期记忆持久化，如用户偏好等。
            checkpointer=CHECKPOINT,                # 检查点，短期记忆，设置之后配合thread_id可实现连续会话
            context_schema=FireLogisticsContext,    # 传递一个Pydantic类，将根据属性提取参数。1.状态固化与规范化，强行规定了 Agent 的记忆里只能存什么、必须存什么，运行时会严格维护该字段；
                                                    # 2.引导大模型进行结构化输入/输出（在每一轮对话，不止最后一轮）    3. 多步骤/多 Agent 之间的信息传递 
            # response_format={"type": "json_object"},# 响应格式 (这个应该限制了json格式，但可能漏字段，更推荐2) 2.同样可以传入Pydantic类来提取格式（部分框架支持直接传 Pydantic，或用 pydantic_to_to_json_schema 转换）
        )
    except Exception as e:
        logger.error(f"主Agent创建失败，原因：{e}")
        raise RuntimeError("因主Agent创建失败，无法构建智能体")
    logger.info("主Agent创建完成")
    return main_agent


# ============================================================
# Agent 懒加载代理（兼容同步/异步两种初始化场景）
# ============================================================

async def _create_agent():
    """创建 Agent 实例（供 _AgentProxy 调用）"""
    return await create_main_agent()


class _AgentProxy:
    """
    懒加载 Agent 代理类

    兼容以下两种使用场景：
    1. 同步环境（如 agent_test.py 控制台）：在模块导入后、事件循环启动前初始化
    2. 异步环境（如 FastAPI 后端）：通过 get_agent_async() 在事件循环中初始化

    当直接访问 agent 对象的属性/方法时，代理会自动触发初始化并委托调用。
    """

    def __init__(self):
        self._agent = None

    @property
    def _is_initialized(self):
        """检查底层 agent 是否已初始化"""
        return self._agent is not None

    def _ensure_initialized(self):
        """
        确保 agent 已初始化（同步方式）

        如果没有运行中的事件循环，使用 asyncio.run() 创建 agent。
        如果事件循环正在运行，抛出 RuntimeError 提示使用 get_agent_async()。
        """
        if self._agent is not None:
            return self._agent

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                raise RuntimeError(
                    "Agent 尚未初始化且当前在事件循环中，"
                    "请使用 await get_agent_async() 获取 agent"
                )
        except RuntimeError as e:
            if "Agent 尚未初始化" in str(e):
                raise
            # 没有事件循环，继续初始化

        self._agent = asyncio.run(_create_agent())
        return self._agent

    def __getattr__(self, name):
        return getattr(self._ensure_initialized(), name)

    def __repr__(self):
        if self._agent is None:
            return "<AgentProxy (not initialized)>"
        return repr(self._agent)

agent = _AgentProxy()

def get_agent():
    """
    获取 Agent 对象,增加懒加载方式
    如果Agent尚未创建，则同步创建他
    """
    global agent    # 声明全局变量，而非举报变量
    if isinstance(agent, _AgentProxy):
        if agent._is_initialized:
            return agent
        return agent._ensure_initialized()
    return agent


async def get_agent_async():
    """
        异步获取 agent 实例，懒加载方式

        适用于在事件循环中运行时调用（如 FastAPI 的 lifespan）。
        如果 agent 已通过 get_agent() 同步初始化，则直接返回。

        Returns:
            CompiledStateGraph: Agent 实例
    """
    global agent
    if isinstance(agent, _AgentProxy):
        if agent._is_initialized:
            return agent
        agent._agent = await create_main_agent()
        return agent._agent
    return agent
