"""
技能中间件，在agent周期执行前，比对本地和沙箱中的数据，进行同步，
且发生变化时，自动插入systemmessage，提示agent出现可以技能。
"""
import hashlib
from pathlib import Path
from typing import Any, Dict
from langchain_core.messages import SystemMessage
from deepagents.backends.sandbox import BaseSandbox
from langchain.agents.middleware.types import AgentState
from langgraph.runtime import Runtime  # 使用通用的沙箱后端协议
from unitl_tools.logger import get_logger
from langchain.agents.middleware import AgentMiddleware
import asyncio
from config import LOCAL_SKILLS_DIR,SANDBOX_SKILLS_ROOT

logger = get_logger(__name__)

class SkillsSyncMiddleware(AgentMiddleware):
    """
    继承该类，可在agent执行时刻插入操作，该类主要用于技能同步
    """ 
    def __init__(self,backend:BaseSandbox):
        super().__init__()
        self.backend = backend
        # 缓存本地哈希值，避免重复同步
        self.local_hash: Dict[str, str] = {}
    
    def before_agent(self, state: Dict[str, Any], runtime: Any) -> Dict[str, Any] | None:
        new_skills = self._sync_files()
        if new_skills:
            return self._make_notification(new_skills)
        return None
    
    async def abefore_agent(self, state: AgentState[Any], runtime: Runtime[None]) -> Dict[str, Any] | None:
        # 使用loop.run_in_executor，在异步函数中调用同步函数
        loop = asyncio.get_running_loop()
        new_skills = await loop.run_in_executor(None, self._sync_files)
        if new_skills:
            return self._make_notification(new_skills)
        return None
    
    def _sync_files(self)->list[str]:
        """
        比对本地和沙箱中的技能，将新增和修改上传到沙箱
        returns:
                返回新增的技能目录
        """
        # 本地技能目录 两个目录需要配置config导入
        local_skills_dir = Path(LOCAL_SKILLS_DIR)
        if not local_skills_dir.exists():
            return []
        
        updated_skills:list[str] = []
        for skill_dir in local_skills_dir.iterdir():
            if skill_dir.is_dir():
                # 判断是不是文件夹
                if not skill_dir.is_dir():
                    continue
                skill_name = skill_dir.name
                sandbox_skill_dir = f"{SANDBOX_SKILLS_ROOT}/{skill_name}"
                files_to_upload:list[tuple[str, bytes]] = []
                has_changed = False
                for file in skill_dir.rglob("*"):   # 递归遍历所有子项  iterdir遍历直接子项
                    if not file.is_file():
                        continue
                    # 存入相同的相对路径
                    rel_path = file.relative_to(skill_dir).as_posix()   # 相对路径 as_posix返回字符串将路径分隔符转换为当前操作系统的路径分隔符 \  /
                    sandbox_path = f"{sandbox_skill_dir}/{rel_path}"
                    with open(file, "rb") as f:
                        file_content = f.read()
                    local_hash = hashlib.md5(file_content).hexdigest()
                    cache_key = f"{skill_name}:{rel_path}"
                    # 本地哈希值未变化，跳过本文件，若有变化，继续走
                    if self.local_hash.get(cache_key) == local_hash:
                        continue

                    #对比沙箱数据  （确定沙箱同地址有无文件，有下载文件，下载后提取第一个，处理为byte类型，计算md5，比对本地，相同则跳过）
                    
                    check = self.backend.execute(f"test -f {sandbox_path}")   ## 1. 检查沙箱中是否已存在该文件
                    if check.exit_code == 0:
                        try:
                            results = self.backend.download_files([sandbox_path])
                            if results and results[0].content and not results[0].error:
                                remote_content = results[0].content
                                if isinstance(remote_content, str):
                                    remote_content = remote_content.encode("utf-8")
                                remote_hash = hashlib.md5(remote_content).hexdigest()
                                if remote_hash == local_hash:
                                    self.local_hash[cache_key] = local_hash
                                    continue

                        except Exception:
                            pass  # 读取失败，需要上传

                    files_to_upload.append((sandbox_path, file_content))
                    has_changed = True

                if has_changed:
                    self.backend.upload_files(files_to_upload)
                    updated_skills.append(skill_name)
        return updated_skills
    
    def _make_notification(self, updated_skills: list[str]):
        """
        生成通知信息
        """
        skills_list = "\n".join(f"{name}" for name in updated_skills)
        notice = (
            f"以下技能已更新:\n"
            f"{skills_list}\n"
        )
        return {"messages": [SystemMessage(content=notice)]}

                    




