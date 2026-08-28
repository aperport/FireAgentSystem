import pytest
from pathlib import Path
from graph_rag.ingestion.doc_parser.pdf_parser import ScanPdfTransformer

path = Path(__file__).parent


@pytest.mark.parametrize("pdf_path, result", [("../../test_data/test.pdf", "Test"),])
def test_pdf_extract(pdf_path, result):
    pdf_path = (path / pdf_path).resolve()
    transformer = ScanPdfTransformer(str(pdf_path))
    assert transformer.pdf_extract().strip() == result
