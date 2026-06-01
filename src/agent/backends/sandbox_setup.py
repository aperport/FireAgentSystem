"""
opensandbox沙箱的初始化，以及文件播种模块
作用：
1.创建或者获取沙箱
2.存入skills文件
"""
import os
import shlex

from opensandbox import SandboxSync
from opensandbox.config import ConnectionConfigSync

from src.agent.backends.custom_opensandbox import OpenSandboxBackend
from unitl_tools.logger import get_logger

logger = get_logger(__name__)

# 沙箱内 skills 文件存放目录
SANDBOX_SKILLS_DIR = "/opt/skills"

def setup_sandbox(config, sandbox_id=None, image=None) -> OpenSandboxBackend:
    """
    尝试按照id重连沙箱，若未找到，或者沙箱已失效，则创建一个新的沙箱，并将技能文件播种到沙箱中，以及python必要的环境变量
    和依赖，并返回一个OpenSandboxBackend对象
    Args:
        config: 配置对象，需包含 api_key、domain、skills_dir 属性
        sandbox_id: 沙箱id，如果不传则创建一个新的沙箱
        image: 沙箱镜像，如果不传则使用默认镜像
    Returns:
        OpenSandboxBackend对象
    """
    connection_config = ConnectionConfigSync(
        domain=getattr(config, "domain", "api.opensandbox.io"),
        api_key=config.api_key,
        
    )

    sandbox = None
    if sandbox_id:
        try:
            logger.info(f"尝试重连沙箱: {sandbox_id}")
            sandbox = SandboxSync.connect(
                sandbox_id,
                connection_config=connection_config,
            )
            sandbox.get_info()
            logger.info(f"沙箱重连成功: {sandbox_id}")
        except Exception as e:
            logger.warning(f"沙箱重连失败 ({sandbox_id}): {e}，将创建新沙箱")
            sandbox = None

    if sandbox is None:
        image = image or getattr(config, "image", None) or "ubuntu"
        logger.info(f"创建新沙箱，镜像: {image}")
        sandbox = SandboxSync.create(
            image=image,
            connection_config=connection_config,
        )
        logger.info(f"新沙箱创建成功: {sandbox.id}")

    backend = OpenSandboxBackend(sandbox=sandbox)

    _ensure_dirs(backend)
    _send_skills_files(backend, config.skills_dir)
    create_environment_variables(backend)

    logger.info(f"沙箱初始化完成: {backend.id}")
    return backend


def _ensure_dirs(backend: OpenSandboxBackend) -> None:
    """
    确保沙箱内的存放skills的目录存在
    Args:
        backend: OpenSandboxBackend对象
    """
    backend.execute(f"mkdir -p {shlex.quote(SANDBOX_SKILLS_DIR)}")
    logger.debug(f"skills 目录已确保存在: {SANDBOX_SKILLS_DIR}")


def create_environment_variables(backend: OpenSandboxBackend) -> None:
    """
    在沙箱内创建必要的环境变量,如python环境，及skills需要的第三方依赖
    Args:
        backend: OpenSandboxBackend对象
    """
    # 创建 skills 专用虚拟环境
    result = backend.execute("python3 -m venv /opt/skills-venv")
    if result.exit_code != 0:
        logger.warning(f"创建 venv 失败: {result.output}")
        return
    logger.debug("skills-venv 创建成功")

    # 如果存在 requirements.txt，安装依赖
    check = backend.execute(f"test -f {shlex.quote(SANDBOX_SKILLS_DIR)}/requirements.txt")
    if check.exit_code == 0:
        logger.info("正在安装 skills 依赖...")
        install_result = backend.execute(
            f"/opt/skills-venv/bin/pip install -r {shlex.quote(SANDBOX_SKILLS_DIR)}/requirements.txt"
        )
        if install_result.exit_code != 0:
            logger.warning(f"依赖安装失败: {install_result.output}")
        else:
            logger.debug("skills 依赖安装完成")


def _send_skills_files(backend: OpenSandboxBackend, skills_dir: str) -> None:
    """
    将skills文件夹中的文件发送到沙箱内的指定目录，对于重复文件不进行覆盖。
    Args:
        backend: OpenSandboxBackend对象
        skills_dir: 本地skills文件夹路径
    """
    if not os.path.isdir(skills_dir):
        logger.warning(f"skills 目录不存在: {skills_dir}")
        return

    files_to_upload: list[tuple[str, bytes]] = []

    for root, _, files in os.walk(skills_dir):
        for filename in files:
            local_path = os.path.join(root, filename)
            rel_path = os.path.relpath(local_path, skills_dir)
            remote_path = f"{SANDBOX_SKILLS_DIR}/{rel_path}"

            # 检查远程文件是否已存在，存在则跳过不覆盖
            check = backend.execute(f"test -f {shlex.quote(remote_path)}")
            if check.exit_code == 0:
                logger.debug(f"文件已存在，跳过: {remote_path}")
                continue

            # 确保远程父目录存在
            parent = os.path.dirname(remote_path)
            backend.execute(f"mkdir -p {shlex.quote(parent)}")

            with open(local_path, "rb") as f:
                files_to_upload.append((remote_path, f.read()))

    if files_to_upload:
        logger.info(f"正在上传 {len(files_to_upload)} 个 skills 文件...")
        results = backend.upload_files(files_to_upload)
        failed = [r.path for r in results if r.error]
        if failed:
            logger.warning(f"以下文件上传失败: {failed}")
        else:
            logger.debug("skills 文件全部上传完成")
    else:
        logger.debug("无新文件需要上传")
