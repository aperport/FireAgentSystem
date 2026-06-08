"""
技能中间件，在agent周期执行前，比对本地和沙箱中的数据，进行同步，
且发生变化时，自动插入systemmessage，提示agent出现可以技能。
"""

from unitl_tools.logger import get_logger
from langchain.agents.middleware import AgentMiddleware

logger = get_logger(__name__)

class SkillsSyncMiddleware(AgentMiddleware):
    """
    继承该类，可在agent执行时刻插入操作，该类主要用于技能同步
    """ 
    