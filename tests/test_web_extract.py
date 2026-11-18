"""추출기 단위 테스트: txt/md 성공, pdf·docx 임시 파일 검증, hwpx zip 픽스처,
구형 hwp 는 쉬운 오류, 손상 파일 오류 메시지."""

from __future__ import annotations

import zipfile

import pytest

from coursespec.web.extract import HWP_UNSUPPORTED_MESSAGE, extract_sources, extract_text
from coursespec.web.errors import ExtractionError


def _minimal_pdf(text: str) -> bytes:
    """텍스트 한 줄이 있는 아주 작은 PDF 를 만든다 (xref 오프셋 포함)."""
    text_bytes = text.encode("latin-1")
    stream = b"BT /F1 12 Tf 72 720 Td (" + text_bytes + b") Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


def test_txt_extract():
    text = extract_text("메모.txt", "첫째 줄\n둘째 줄\n".encode("utf-8"))
    assert "첫째 줄" in text
    assert "둘째 줄" in text


def test_markdown_extract():
    text = extract_text("강의노트.md", "# 제목\n본문입니다.".encode("utf-8"))
    assert "# 제목" in text
    assert "본문입니다" in text


def test_txt_wrong_encoding_clear_error():
    with pytest.raises(ExtractionError) as excinfo:
        extract_text("자료.txt", "안녕하세요".encode("euc-kr"))
    assert "UTF-8" in excinfo.value.message


def test_txt_empty_clear_error():
    with pytest.raises(ExtractionError) as excinfo:
        extract_text("빈.txt", b"   \n ")
    assert "없습니다" in excinfo.value.message


def test_pdf_extract():
    data = _minimal_pdf("Hello PDF")
    text = extract_text("원고.pdf", data)
    assert "Hello PDF" in text


def test_pdf_damaged_clear_error():
    with pytest.raises(ExtractionError) as excinfo:
        extract_text("손상.pdf", b"not a real pdf at all")
    assert "PDF" in excinfo.value.message


def test_docx_extract():
    import docx

    document = docx.Document()
    document.add_paragraph("1주차 개요")
    document.add_paragraph("학습 목표를 세웁니다.")
    import io

    buf = io.BytesIO()
    document.save(buf)
    text = extract_text("강의계획서.docx", buf.getvalue())
    assert "1주차 개요" in text
    assert "학습 목표를 세웁니다" in text


def test_docx_damaged_clear_error():
    with pytest.raises(ExtractionError) as excinfo:
        extract_text("깨진.docx", b"PK\x03\x04 broken")
    assert "Word" in excinfo.value.message


def _hwpx_bytes(text: str) -> bytes:
    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<hp:content xmlns:hp="http://www.hwpml.org/content">'
        f"<hp:body><hp:section><hp:p><hp:t>{text}</hp:t></hp:p></hp:section></hp:body>"
        "</hp:content>"
    )
    buf = _zip_bytes({"Contents/content.hpf": xml.encode("utf-8")})
    return buf


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buf.getvalue()


def test_hwpx_extract():
    text = extract_text("문서.hwpx", _hwpx_bytes("한글 문서 본문입니다."))
    assert "한글 문서 본문입니다" in text


def test_hwpx_damaged_clear_error():
    with pytest.raises(ExtractionError) as excinfo:
        extract_text("깨진.hwpx", b"this is not a zip")
    assert ".hwpx" in excinfo.value.message


def test_hwp_legacy_friendly_error():
    with pytest.raises(ExtractionError) as excinfo:
        extract_text("구버전.hwp", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 legacy ole")
    assert excinfo.value.message == HWP_UNSUPPORTED_MESSAGE


def test_unsupported_extension():
    with pytest.raises(ExtractionError) as excinfo:
        extract_text("자료.pptx", b"whatever")
    assert "읽을 수 없습니다" in excinfo.value.message


def test_extract_sources_continues_after_failure():
    files = [
        ("메모.txt", "정상 메모".encode("utf-8")),
        ("구버전.hwp", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1 legacy"),
        ("노트.md", "두 번째 자료".encode("utf-8")),
    ]
    sources, warnings = extract_sources(files)
    assert [name for name, _ in sources] == ["메모.txt", "노트.md"]
    assert len(warnings) == 1
    assert "아직 바로 읽지 못합니다" in warnings[0]
