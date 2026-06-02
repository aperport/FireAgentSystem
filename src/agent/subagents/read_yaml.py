"""
读取agents中的yaml文件，将其转化为create_deep_agent()方法中的subagents参数，
且过程中可能需要对skills、tools及mcp等进行校验，确定系统中存在工具和技能等。
"""

from pathlib import Path
import yaml

YamlPath = Path(__file__).parent / "agents"
def load_yaml(yaml_path: Path | None = None) :
    """读取 agents 目录下的 YAML 文件，返回 subagents 参数列表"""
    if yaml_path is None:
        yaml_path = YamlPath
    subagents = []
    for yaml_file in yaml_path.iterdir():
        if yaml_file.suffix == ".yaml":
            print(f"Loading {yaml_file}")
            try:
                with open(yaml_file, "r", encoding="utf-8") as f:
                    conment = yaml.safe_load(f)

                    
            except Exception as e:
                print(f"Error loading {yaml_file}: {e}")
    return subagents

                    

