"""
子 Agent YAML 解析与工具组装模块。

功能：
    1. load_yaml() — 读取 agents/ 目录下的 YAML 文件，解析为子 Agent 配置列表
    2. resolve_tools() — 根据 YAML 配置从 tool_map 中匹配实际工具实例
    3. assemble_subagents() — 完整流程：加载YAML + 加载MCP工具 + 组装

当前子 Agent YAML 配置：
    fire_qa_assistant.yaml      — 知识问答助手（GraphRAG检索工具）
    fire_management_analyst.yaml — 管理分析助手（报表评鉴+明细+图遍历工具）

工具匹配方式：
    - group 前缀匹配：name.startswith("group_") → 匹配同组所有工具
    - include 名称匹配：name in tool_map → 精确匹配单个工具
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
                    content = yaml.safe_load(f)
                    # 对必填项进行校验
                    missing_requirements = _validate_subagent_config(content)
                    if missing_requirements:
                        logger.warning(f"子智能体{yaml_file.name}配置文件缺少必填项：{missing_requirements}")
                        continue
                    subagents.append(content)
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




async def assemble_subagent(subagents:list | None=None,tool_map:dict[str,BaseTool] | None=None) -> list:
    """
    目前加载后的子智能体中工具仅有名称，此方法对将实例工具与子智能体进行组装，实现功能
    args:
       subagents: 子智能体列表
       tool_map: 工具映射
    returns:
       list: 子智能体集合
    """
    if not subagents:
        subagents  = load_yaml()
        logger.info(f"已加载子智能体：{subagents}")
    if not tool_map:
        tool_map = await load_mcp_tools()
        logger.info(f"已加载工具：{tool_map}")
    try:
        new_subagents = []
        for subagent in subagents: 
            subagent_tools = resolve_tools(subagent,tool_map)
            subagent["tools"] = subagent_tools
            logger.info(f"已组装子智能体工具：{subagent.get('name')}")
            new_subagents.append(subagent)
        return new_subagents
    except Exception as e:
        logger.error(f"子智能体组装失败，原因：{e}")
        return []
        
    
