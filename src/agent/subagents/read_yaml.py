"""
读取agents中的yaml文件，将其转化为create_deep_agent()方法中的subagents参数，
且过程中可能需要对skills、tools及mcp等进行校验，确定系统中存在工具和技能等。
"""
from langchain.tools import BaseTool
from pathlib import Path
import yaml
from agent.tools.MCP_client import load_mcp_tools
from mcp_server import tools
from unitl_tools.logger import get_logger

logger = get_logger(__name__)
YamlPath = Path(__file__).parent / "agents"
def load_yaml(yaml_path: Path | None = None) :
    """读取 agents 目录下的 YAML 文件，返回 subagents 参数列表"""
    if yaml_path is None:
        yaml_path = YamlPath
        logger.info(f"已选用默认路径： {yaml_path}")
    subagents = []
    for yaml_file in yaml_path.iterdir():
        if yaml_file.suffix == ".yaml":
            logger.info(f"加载 {yaml_file}")
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    conment = yaml.safe_load(f)
                    # 对必填项进行校验
                    missing_requirements = _validate_subagent_config(conment)
                    if missing_requirements:
                        logger.warning(f"子智能体{yaml_file.name}配置文件缺少必填项：{missing_requirements}")
                        continue
                    subagents.append(conment)
            except Exception as e:
                logger.warning(f"子智能体{yaml_file.name}加载失败，原因：{e}")
    return subagents

def _validate_subagent_config(data: dict) -> list[str]:
    """
    验证子智能体配置文件
    args:
        data: 子智能体配置文件数据
        filename: 子智能体配置文件名
    returns:
        list[str]: 验证结果(错误信息列表)
    """
    requirements = ["name", "description", "system_prompt"]
    missing_requirements = [req for req in requirements if req not in data]

    if "tools" in data:
        if not isinstance(data["tools"], list):
            missing_requirements.append("tools应为列表形式")
    return missing_requirements



def resolve_tools(subagent_config:dict,tool_map:dict[str,BaseTool])->list[BaseTool]:
    """
    根据YAML配置文件从tool_map中解析出实际工具列表工具
    args:
       subagent_config: 子智能体配置文件
       tool_map: 工具映射
    returns:
       list[BaseTool]: 工具
    """ 
    try:
        tools_config = subagent_config.get("tools",{})
        selected_tools = set()

    # 1. 先进行组匹配
        if "group" in tools_config:
            group_name = tools_config["group"]
            for name,tool in tool_map.items():  #items()返回字典中的键值对
            #通过匹配开头拿到工具集合
                if name.startswith(f"{group_name}_"):
                    selected_tools.add(tool)

    # 2. 再进行名称匹配
        if "include" in tools_config:
            for name in tools_config["include"]:
                if name in tool_map:
                    selected_tools.add(tool_map[name])
        return [tool for tool in selected_tools ]
    except Exception as e:
        logger.error(f"子智能体配置文件解析失败，原因：{e}")
        return []

async def assemble_subagents(subagents: list | None = None,tool_map:dict[str,BaseTool] | None = None)->list:
    """
    组装子智能体，读取后，需要对子智能体的工具进行重新载入，作为真正的工具
    args:
        subagents: 子智能体列表，工具为名称
        tool_map: 工具映射
    returns:
        list: 子智能体列表
    """
    subagent_list = []
    # 获取子智能体列表和工具列表，之后从子智能体中解析出工具，将工具装入智能体的字典，组成新列表，传给主agent
    if not subagents:
        logger.info("子智能体为空，从agents目录下加载子智能体")
        subagents = load_yaml()
    if not tool_map:
        logger.info("工具为空，从MCP加载工具")
        tool_map = await load_mcp_tools()
    try:
        for subagent in subagents: 
            subaagent_tools:list[BaseTool] = resolve_tools(subagent,tool_map)
            logger.info(f"已加载子智能体：{subagent['name']}")
            subagent["tools"] = subaagent_tools
            subagent_list.append(subagent)
            logger.info(f"子智能体：{subagent['name']}加载完成")
    except Exception as e:
        logger.error(f"子智能体加载失败，原因：{e}")
    return subagent_list
            
    
