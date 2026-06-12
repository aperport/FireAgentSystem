"""
主Agent入口模块，
使用deepagents 创建一个示例，将所有组件串联起来，成为一个可运行的智能助手，使用async graph factory的模式，每次调用创建新沙箱
"""



import asyncio
import logging
import os
import sys
from deepagents import create_deep_agent
from langchain_core.runnables import RunnableConfig
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)
from agent.schema import ProcurementContext
from agent.tools import assign_skills
from memoy.prompts import system_prompt
from agent.backends.sandbox_setup import setup_sandbox
from agent.config import CHECKPOINT, LOCAL_AGENTS_MD, STORE, SUMMARY_MODEL
from agent.middleware_config import create_analyst_middleware, create_order_middleware
from agent.middlewares.context_injection import ContextInjectionMiddleware
from agent.middlewares.memory_update import MemoryUpdateMiddleware
from agent.middlewares.skills_sync import SkillsSyncMiddleware
from agent.subagents.read_yaml import assemble_subagents
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
        raise RuntimeError(f"因沙箱配置失败，无法构建智能体")
    
    # 上传Agent.md到沙箱
    logger.info("正在上传Agent.md到沙箱")
    ag_md_content = LOCAL_AGENTS_MD.read_text()
    sandbox_backend.upload_files([("Agent.md", ag_md_content.encode("utf-8"))])
    logger.info("上传Agent.md到沙箱成功")

    # CompositeBackend 分流
        # /AGENTS.md          → 沙箱 default 路由（OpenSandbox已上传）
        # /memories/          → StoreBackend（按 user_id 隔离用户偏好）
        # /persisted-skills/  → StoreBackend（按 Agent scope 组织技能）
        # 其余路径（临时文件、代码执行）保留在沙箱。
    logger.info("主Agent创建完成，开始进行分流")
    backend = lambda rt: CompositeBackend(
        default=sandbox_backend,
        routes={
            "memories": StoreBackend(
                runtime=rt,
                namespace=lambda rt : (getattr(rt.runtime.context, 'user_id', 'test'),),
            ),
            "persisted-skills": StoreBackend(
                runtime=rt,
                namespace=lambda rt : SKILLS_STORE_NAMESPACE,
            ),
        }
    )

    # MCP工具加载
    logger.info("开始加载MCP工具")
    try:
        all_mcp_tools = await load_mcp_tools()
        logger.info("MCP工具加载完成")
    except Exception as e:
        logger.error(f"MCP工具加载失败，原因：{e}")
        raise RuntimeError(f"因MCP工具加载失败，无法构建智能体")
    
    # 创建技能管理工具 
    assign_skill = assign_skills.create_assign_skill_tool(
        sandbox_backend,
        store=STORE,
        skills_namespace=SKILLS_STORE_NAMESPACE,
    )
    download_sandbox_file = create_download_tool(sandbox_backend, DOWNLOAD_DIR)
    
    # 工具池构建
    logger.info("开始构建工具池")

    available_tools = list(all_mcp_tools.values())

    logger.info("工具池构建完成,共计{}个工具".format(len(available_tools)))

    # 子Agent的Yaml加载
    logger.info("开始加载子Agent")
    try:
        subagents  = assemble_subagents()
        if not subagents :
            logger.error("子Agent加载失败，原因：子Agent为空,将使用主智能体运行")
        logger.info("子Agent加载完成")
    except Exception as e:
        logger.error(f"子Agent加载失败，原因：{e}")
        raise RuntimeError(f"因子Agent加载失败，无法构建智能体")

    # 创建子Agent中间件,此处使用了子智能体，需根据实际业务设置
    logger.info("开始创建子Agent中间件")  
    extra_mid = {
        "procurement-analyst": create_analyst_middleware(SUMMARY_MODEL, backend),   # 缺少大语言模型
        "procurement-order": create_order_middleware(),        
    }

    # 子智能体工具解析 ，上边已进行内部解析，此处跳过了

    

    # 主智能体中间件
    logger.info("开始创建主Agent中间件")
    try:
        main_mid = [
            ContextInjectionMiddleware(),
            SkillsSyncMiddleware(sandbox_backend),
            #build_summarization_middleware(backend, SUMMARY_MODEL),
            MemoryUpdateMiddleware(model=SUMMARY_MODEL),
            ModelCallLimitMiddleware(run_limit=50),    # 限制模型调用次数
            ToolCallLimitMiddleware(run_limit=200),    # 限制工具调用次数
        ]
    except Exception as e:
        logger.error(f"主Agent中间件创建失败，原因：{e}")
        raise RuntimeError(f"因主Agent中间件创建失败，无法构建智能体")
    logger.info("主Agent中间件创建完成")

    # 创建主Agent
    logger.info("开始创建主Agent")
    try:
        main_agent = create_deep_agent(
            model=SUMMARY_MODEL,
            system_prompt=system_prompt,
            skills= ["/skills/main/"],
            memory=["/memories/"],    # AGENT.md的文件夹
            tools =[assign_skill, download_sandbox_file],
            #subagents=subagents,
            middleware=main_mid,
            backend=backend,
            store=STORE,   # 持久化 
            checkpointer=CHECKPOINT,
            context_schema=ProcurementContext    # 传递当前用户信息
        )
    except Exception as e:
        logger.error(f"主Agent创建失败，原因：{e}")
        raise RuntimeError(f"因主Agent创建失败，无法构建智能体")
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


# agent 实例，初始化为懒加载代理，由 get_agent() / get_agent_async() 函数触发初始化
agent = _AgentProxy()


def get_agent():
    """
    获取 agent 实例，懒加载方式（同步）

    如果 agent 尚未初始化，则同步创建它。
    注意：不能在运行中的事件循环内调用此函数。

    Returns:
        CompiledStateGraph: Agent 实例
    """
    global agent
    if isinstance(agent, _AgentProxy):
        if agent._is_initialized:
            return agent._agent
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
            return agent._agent
        agent._agent = await _create_agent()
        return agent._agent
    return agent