from deepagents.backends.sandbox import BaseSandbox
from opensandbox import SandboxSync


from unitl_tools.logger import get_logger

logger = get_logger(__name__)

class OpenSandboxBackend(BaseSandbox):
    """
    基于OpenSandboxBackend的沙盒后端，继承了deepagents中BaseSandbox类的文件操作方法
    仅需要实现execute、download_files 和 upload_files。
    """
    def __init__(self,*,sandbox:SandboxSync,timeout:int=60 * 60,
                 sync_polling_interval: SyncPollingInterval = 0.1,):
