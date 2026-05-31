"""
opensandbox沙箱的初始化，以及文件播种模块
作用：
1.创建或者获取沙箱
2.存入skills文件
"""

def setup_sandbox(config,sandbox_id=None,image=None)->OpenSandboxBackend: