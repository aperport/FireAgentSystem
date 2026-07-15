"""
OpenSandbox 后端封装 — 适配器模式，将 SandboxSync 封装为 BaseSandbox 协议。

实现 BaseSandbox 接口的方法：
    - execute()       — 在沙箱中执行命令
    - upload_files()  — 上传文件到沙箱
    - download_files() — 从沙箱下载文件

供 CompositeBackend 的 default 路由使用，
管理助手可在沙箱中执行 Python 代码进行自定义分析。
"""
from datetime import timedelta
from typing import Literal

from deepagents.backends.protocol import ExecuteResponse, FileDownloadResponse, FileUploadResponse
from deepagents.backends.sandbox import BaseSandbox
from opensandbox import SandboxSync
from opensandbox.models.execd import RunCommandOpts
from opensandbox.models.filesystem import WriteEntry
from util_tools.logger import get_logger

logger = get_logger(__name__)


class OpenSandboxBackend(BaseSandbox):
    """
    基于OpenSandboxBackend的沙盒后端，继承了deepagents中BaseSandbox类的文件操作方法
    仅需要实现execute、download_files 和 upload_files。
    """
    def __init__(self, *, sandbox: SandboxSync, timeout: int = 60 * 60):
        """
        创建一个OpenSandboxBackend实例
        :param sandbox: 要包装的现有sandbox
        :param timeout: 命令执行超时时间
        """
        logger.info("正在进行沙箱初始化，沙箱id：%s", sandbox.id)
        self._sandbox = sandbox
        self._timeout = timeout
        logger.debug("OpenSandbox 初始化完成，默认超时时间=%d秒", timeout)

    @property
    def id(self) -> str:
        """
        获取沙箱id（实现 BaseSandbox 的抽象属性）
        :return: 沙箱id
        """
        sandbox_id = self._sandbox.id
        logger.debug("获取沙盒 ID: %s", sandbox_id)
        return sandbox_id

    # 沙箱中非交互式 shell 不会加载 /etc/profile，需要手动注入环境变量，确保沙箱内可以找到必要的依赖
    SANDBOX_PATH = (
        "/opt/skills-venv/bin:"
        "/opt/python/versions/cpython-3.11.14-linux-x86_64-gnu/bin:"
        "/opt/go/1.25.5/bin:"
        "/opt/node/v22.2.0/bin:"
        "/usr/lib/jvm/java-21-openjdk-amd64/bin:"
        "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
    )

    def execute(
        self,
        command: str,
        *,
        timeout: int | None = None,
    ) -> ExecuteResponse:
        """
        在沙箱内执行一条shell命令
        :param command: 要执行的 Shell 命令字符串。
        :param timeout: 等待命令完成的最大时间（秒）。
                如果为 None，则使用后端默认的超时时间。
        :return: ExecuteResponse，包含命令输出和退出码
        """
        effective_timeout = timeout if timeout is not None else self._timeout
        full_command = f"export PATH=\"{self.SANDBOX_PATH}:$PATH\" && \"{command}\""
        # 一段时间后杀死对象，用来限制进程时间
        opts = RunCommandOpts(timeout=timedelta(seconds=effective_timeout))

        logger.debug("执行命令: %s，timeout=%d", command, effective_timeout)

        try:
            execution = self._sandbox.commands.run(full_command, opts=opts)
        except Exception:
            logger.exception("命令执行异常: %s", command)
            return ExecuteResponse(output="沙箱命令执行失败", exit_code=None)

        #提取标准输出与标准错误，并合并输出
        stdout = ""
        if execution.logs.stdout:
            stdout = "\n".join(line.text for line in execution.logs.stdout)

        stderr = ""
        if execution.logs.stderr:
            stderr = "\n".join(line.text for line in execution.logs.stderr)

        output = "\n".join(part for part in (stdout, stderr) if part)

        exit_code = execution.exit_code
        if execution.error:
            output = f"[{execution.error.name}] {execution.error.value}\n{output}"

        logger.debug("命令执行完成，exit_code=%s, output长度=%d", exit_code, len(output))

        return ExecuteResponse(
            output=output,
            exit_code=exit_code,
        )

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        """
        从沙箱批量下载文件，支持部分成功
        :param paths: 沙箱内的文件路径列表
        :return: FileDownloadResponse 列表，每个元素包含文件内容或错误信息
        """
        responses: list[FileDownloadResponse] = []
        for path in paths:
            try:
                content = self._sandbox.files.read_file(path)
                if isinstance(content, str):
                    content = content.encode("utf-8")
                responses.append(FileDownloadResponse(path=path, content=content))
            except Exception as e:
                logger.exception("下载文件失败 %s", path)
                responses.append(FileDownloadResponse(path=path, content=None, error=str(e)))
        return responses

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        """
        批量上传文件到沙箱，支持部分成功
        :param files: (文件路径, 文件内容字节) 元组列表
        :return: FileUploadResponse 列表，每个元素包含操作错误信息（成功时为 None）
        """
        responses: list[FileUploadResponse] = []
        for path, data in files:
            try:
                entry = WriteEntry(path=path, data=data)
                self._sandbox.files.write_files([entry])
                responses.append(FileUploadResponse(path=path))
            except Exception as e:
                logger.exception("上传文件失败 %s", path)
                responses.append(FileUploadResponse(path=path, error=str(e)))
        return responses
