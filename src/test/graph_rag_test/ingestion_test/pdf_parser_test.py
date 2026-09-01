import pytest
from pathlib import Path
from graph_rag.ingestion.doc_parser.pdf_parser import ScanPdfTransformer
from graph_rag.ingestion.doc_parser.dispatcher import file_geuss

path = Path(__file__).parent


@pytest.mark.parametrize("pdf_path, result", [("../../test_data/test.pdf", "Test"),])
def test_pdf_extract(pdf_path, result):
    pdf_path = (path / pdf_path).resolve()
    transformer = ScanPdfTransformer(str(pdf_path))
    assert transformer.pdf_extract().strip() == result


@pytest.mark.parametrize("file_path, result", [("../../test_data/test.pdf", "pdf"),])
def test_file_geuss(file_path, result):
    file_path = (path / file_path).resolve()
    results = file_geuss(str(file_path))
    assert results == result
