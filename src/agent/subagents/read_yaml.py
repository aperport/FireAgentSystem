"""
读取agents中的yaml文件，将其转化为create_deep_agent()方法中的subagents参数，
且过程中可能需要对skills、tools及mcp等进行校验，确定系统中存在工具和技能等。
"""

from pathlib import Path
import yaml
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


def tools_load() ->list[tools]:
    """
    对工具进行校验，比对已有工具和智能体配置文件中的工具是否一致，将工具载入子智能体中，返回工具列表，并且对缺失的工具进行提示
    returns:
        list[tools]: 工具
    """
    pass
            

                    