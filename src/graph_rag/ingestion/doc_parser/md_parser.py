"""
Markdown 直接读取模块 — 读取 Markdown 文件并做标准化处理。

✅ 已实现。处理流程：
    1. 读取 Markdown 文件内容
    2. 标准化处理：
        - 统一标题层级（确保从 # 开始，无跳级）
        - 规范化空白（行尾空格、连续空行）
    3. 提取内嵌图片路径（![alt](path) 标记）
    4. 元数据增强：
        - 确定性层：路径信息 + 顶层标题链（零成本）
        - 增强层：可插拔的 MetadataEnhancer 接口（如 LLM 辅助提取）
    5. 返回 ParsedDocument

已实现方法：
    - parse()             解析单个 Markdown 文件
    - parse_directory()   递归解析目录下所有 Markdown 文件
    - _normalize_headers()   统一标题层级
    - _normalize_whitespace() 规范化空白
    - _extract_images()      提取图片引用
    - _build_base_metadata() 构建基础元数据

适用场景：
    - 已有的 Markdown 格式操作手册
    - 系统导出的巡检/值班报告（markdown格式）
    - 法律规范等结构化 Markdown 文档
    - AGENTS.md 等纯文本文件

输出格式：
    ParsedDocument(text=原始Markdown, images=[...], metadata={source, filename, ...})

⚠️ 已知问题：
    1. parent_id 哈希仅基于文件名（path.stem），同名文件会冲突，
       应改为基于相对路径的哈希
    2. header_chain 使用 path.parts（绝对路径目录），应使用相对路径

待优化：
    - parent_id 改为基于相对路径的稳定哈希
    - header_chain 使用相对路径，避免暴露绝对路径
    - 增加 frontmatter（YAML 头部）解析支持
"""
import hashlib
import re
from pathlib import Path
from util_tools.logger import get_logger
from . import ParsedDocument
from typing import Any, Protocol


logger = get_logger(__name__)

# 匹配 ![alt](path) 和 ![alt](path "title") 两种格式
_IMAGE_PATTERN = re.compile(
    r"!\[([^\]]*)\]\(([^)\s]+)(?:\s+[\"'][^\"']*[\"'])?\)"
)


class MetadataEnhancer(Protocol):
    """元数据增强器基类 — 可插拔接口，供子类实现自定义增强逻辑。

    确定性增强（路径、标题链等）已内置在 MdParser 中，
    此接口用于可选的增强层，如 LLM 辅助提取法规时效性、操作角色等。
    """

    def enhance(self, parsed_doc: ParsedDocument) -> ParsedDocument: ...


class Normalize(Protocol):
    def normalize_headers(self, text: str) -> str: ...

    def normalize_whitespace(self, text: str) -> str: ...


class NormalizeMD:

    def normalize_headers(self, text: str) -> str:
        """统一标题层级 — 确保标题从 # 开始，无跳级。

        例如原文直接从 ## 跳到 #### 会被调整为 ## → ###。
        """
        lines = text.split("\n")
        min_level_seen = None

        # 找到文档中出现的最高标题级别
        for line in lines:
            match = re.match(r"^(#{1,6})\s", line)
            if match:
                level = len(match.group(1))
                if min_level_seen is None or level < min_level_seen:
                    min_level_seen = level

        # 如果最高级别不是 #（一级），则整体提升
        if min_level_seen is not None and min_level_seen > 1:
            offset = min_level_seen - 1
            for i, line in enumerate(lines):
                match = re.match(r"^(#{1,6})\s", line)
                if match:
                    old_level = len(match.group(1))
                    new_level = max(1, old_level - offset)
                    lines[i] = "#" * new_level + line[old_level:]

        return "\n".join(lines)

    def normalize_whitespace(self, text: str) -> str:
        """规范化空白 — 去除行尾空格，合并连续空行。"""
        # 去除行尾空格
        text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
        # 合并连续空行为最多两个换行
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip() + "\n"


def extract_images(text: str) -> list[dict[str, str]]:
    """提取 Markdown 中的图片引用。

    Returns:
        图片信息列表，每项包含 path 和 alt
    """
    images = []
    for match in _IMAGE_PATTERN.finditer(text):
        alt = match.group(1)
        path = match.group(2)
        images.append({"path": path, "alt": alt})
    return images


def build_base_metadata(path: Path, text: str) -> dict[str, Any]:
    """构建基础元数据 — 确定性层，零成本。

    包含字段：
        - source: 文件绝对路径
        - filename: 文件名（含扩展名）
        - suffix: 文件扩展名
        - format: 固定为 "markdown"
        - parent_id: 基于文件名的稳定哈希 ID
        - top_headers: 顶层标题列表（文档的一级标题）
        - header_chain: 从路径和标题推断的层级路径
        - char_count: 字符数
    """
    # 文件基本信息
    metadata: dict[str, Any] = {
        "source": str(path),
        "filename": path.name,
        "suffix": path.suffix.lower(),
        "format": "markdown",
        "char_count": len(text),
    }

    # 基于文件名的稳定哈希 ID
    # ponytail: 基于 path.stem，同名文件会冲突；改用相对路径哈希时升级此处
    metadata["parent_id"] = hashlib.md5(
        path.stem.encode("utf-8")
    ).hexdigest()

    # 提取一级标题作为 top_headers
    top_headers = []
    for line in text.split("\n"):
        match = re.match(r"^#\s+(.+)$", line)
        if match:
            top_headers.append(match.group(1).strip())
    metadata["top_headers"] = top_headers

    # 构建 header_chain：路径目录部分 + 顶层标题
    dir_parts = path.parts[:-1]  # 去掉文件名
    header_chain_parts = list(dir_parts)
    if top_headers:
        header_chain_parts.append(top_headers[0])
    metadata["header_chain"] = " > ".join(header_chain_parts) if header_chain_parts else ""
    return metadata


class MdParser:
    """Markdown 文件解析"""

    def __init__(self, normalizer: Normalize, enhancers: list[MetadataEnhancer] | None = None):
        self.enhancers = enhancers or []
        self.normalizer = normalizer

    def parse(self, file_path: str) -> ParsedDocument:
        """解析单个 Markdown 文件。"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")
        if path.suffix.lower() not in (".md", ".markdown"):
            raise ValueError(f"非 Markdown 文件: {file_path}")

        # 1. 读取原始内容
        text = path.read_text(encoding="utf-8")

        # 2. 标准化处理
        text = self.normalizer.normalize_headers(text)
        text = self.normalizer.normalize_whitespace(text)

        # 3. 提取图片
        images = extract_images(text)

        # 4. 构建基础元数据（确定性层）
        metadata = build_base_metadata(path, text)

        parsed_doc = ParsedDocument(text=text, images=images, metadata=metadata)

        # 5. 执行可插拔的增强器
        for enhancer in self.enhancers:
            try:
                parsed_doc = enhancer.enhance(parsed_doc)
            except Exception as e:
                logger.warning(f"元数据增强器 {enhancer.__class__.__name__} 执行失败: {e}")

        logger.info(f"解析完成: {path.name}, 图片 {len(images)} 张")
        return parsed_doc

    def parse_directory(self, dir_path: str) -> list[ParsedDocument]:
        """递归解析目录下所有 Markdown 文件。"""
        results = []
        dir_path_obj = Path(dir_path)
        if not dir_path_obj.is_dir():
            raise ValueError(f"非目录路径: {dir_path}")

        for md_file in sorted(dir_path_obj.rglob("*.md")):
            try:
                results.append(self.parse(str(md_file)))
            except Exception as e:
                logger.warning(f"解析文件 {md_file} 失败: {e}")

        # 也匹配 .markdown 后缀
        for md_file in sorted(dir_path_obj.rglob("*.markdown")):
            try:
                results.append(self.parse(str(md_file)))
            except Exception as e:
                logger.warning(f"解析文件 {md_file} 失败: {e}")

        logger.info(f"目录解析完成: {dir_path}, 共 {len(results)} 个文档")
        return results
