import pdf_inspector
from util_tools.logger import get_logger
from pathlib import Path
logger = get_logger(__name__)

local_path = Path(__file__).parent
output_path = (local_path / "md_output").resolve()


class ScanPdfTransformer:
    """
    综合提取 PDF 内容，包括文本和嵌入图片
    """

    def __init__(self, pdf_path: str, output_path: Path = output_path):
        self.pdf_path = pdf_path
        self.output_path = output_path
        self.md = None

    def pdf_check(self):
        """检查 PDF 类型，区分哪一页需要 OCR，哪一页可直接扫描提取。"""
        check_result = pdf_inspector.detect_pdf(self.pdf_path)
        logger.info(
            f"PDF 类型检查结果：{check_result.pdf_type},{check_result.pages_needing_ocr}，上述 {len(check_result.pages_needing_ocr)} 页需要 OCR。")

    def pdf_extract(self):
        """提取 PDF 内容，包括文本和嵌入图片。"""
        logger.info("开始提取 PDF 内容。")
        read_result = pdf_inspector.process_pdf(self.pdf_path)
        if not read_result:
            logger.error("提取 PDF 内容失败。")
        self.md = read_result.markdown

    def pdf_write_md(self) -> Path:
        """
        将提取的 PDF 内容 写入md文件，用于后续提取。
        args:
            pdf_path: pdf文件路径
        """
        if not self.md:
            logger.info("md为空，无法写入，请先提取内容")
            raise ValueError("md为空，无法写入，请先提取内容")
        try:
            file_name = Path(self.pdf_path).stem + ".md"
            file_path = Path(self.output_path) / file_name
            file_path.write_text(self.md, encoding="utf-8")
            logger.info(f"PDF 内容已写入 {file_path},文件大小为 {file_path.stat().st_size} 字节。")
            return file_path
        except Exception as e:
            logger.error(f"写入 PDF 内容失败：{e}")
            raise
