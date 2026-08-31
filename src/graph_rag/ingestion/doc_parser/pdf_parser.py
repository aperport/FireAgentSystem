import pdf_inspector
from util_tools.logger import get_logger

logger = get_logger(__name__)


class ScanPdfTransformer:
    """
    综合提取 PDF 内容，包括文本和嵌入图片
    """

    def __init__(self, pdf_path: str, output_path: str | None = None):
        self.pdf_path = pdf_path
        self.output_path = output_path

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
            return None
        return read_result.markdown
