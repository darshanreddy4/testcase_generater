import pytest

from app.ingestion.file_parser import UnsupportedFileTypeError, extract_text


def test_extract_text_from_txt(tmp_path):
    p = tmp_path / "req.txt"
    p.write_text("Users should be able to upload a driver's license.", encoding="utf-8")
    assert "driver's license" in extract_text(p)


def test_extract_text_unsupported_extension(tmp_path):
    p = tmp_path / "req.exe"
    p.write_bytes(b"binary")
    with pytest.raises(UnsupportedFileTypeError):
        extract_text(p)


def test_extract_text_from_csv(tmp_path):
    p = tmp_path / "req.csv"
    p.write_text("field,value\nname,John", encoding="utf-8")
    assert "John" in extract_text(p)
