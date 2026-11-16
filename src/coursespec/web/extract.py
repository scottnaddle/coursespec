"""업로드 자료의 텍스트 추출.

PDF, DOCX, HWPX, 텍스트·마크다운을 읽고, 구형 HWP 바이너리는 쉬운 한국어 오류로 안내한다.
실패는 파일별로 보고하되, 다른 파일·과목 이름만으로도 초안 생성을 계속할 수 있게 한다.
"""

from __future__ import annotations

import io
import zipfile
from xml.etree import ElementTree

from .errors import ExtractionError

# 다루는 확장자 (소문자). 마크다운 변형도 텍스트로 취급한다.
TEXT_SUFFIXES = {".txt", ".md", ".markdown"}
PDF_SUFFIX = ".pdf"
DOCX_SUFFIX = ".docx"
HWPX_SUFFIX = ".hwpx"
HWP_SUFFIX = ".hwp"

SUPPORTED_SUFFIXES = TEXT_SUFFIXES | {PDF_SUFFIX, DOCX_SUFFIX, HWPX_SUFFIX, HWP_SUFFIX}

# 구형 HWP 바이너리는 별도 파서가 없어 읽지 못한다. 조용히 버리지 않고 안내한다.
HWP_UNSUPPORTED_MESSAGE = (
    "이 형식(.hwp)은 아직 바로 읽지 못합니다. "
    "hwpx, pdf, docx, txt로 저장해서 다시 올려 주세요."
)


def _suffix(filename: str) -> str:
    name = (filename or "").lower()
    for suf in (HWPX_SUFFIX, DOCX_SUFFIX, HWP_SUFFIX, PDF_SUFFIX, ".markdown", ".md", ".txt"):
        if name.endswith(suf):
            return suf
    return ""


def extract_text(filename: str, data: bytes) -> str:
    """파일 하나에서 텍스트를 추출한다. 실패하면 ExtractionError 를 던진다."""
    suffix = _suffix(filename)
    if suffix in TEXT_SUFFIXES:
        return _extract_text_file(filename, data)
    if suffix == PDF_SUFFIX:
        return _extract_pdf(filename, data)
    if suffix == DOCX_SUFFIX:
        return _extract_docx(filename, data)
    if suffix == HWPX_SUFFIX:
        return _extract_hwpx(filename, data)
    if suffix == HWP_SUFFIX:
        raise ExtractionError(filename, HWP_UNSUPPORTED_MESSAGE)
    raise ExtractionError(
        filename,
        "이 파일 형식은 읽을 수 없습니다. hwpx, pdf, docx, txt 형식으로 올려 주세요.",
    )


def _extract_text_file(filename: str, data: bytes) -> str:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ExtractionError(
            filename,
            "글자가 깨져 읽지 못했습니다. UTF-8 텍스트 파일로 다시 저장해 주세요.",
        ) from exc
    if not text.strip():
        raise ExtractionError(filename, "파일 안에 읽을 내용이 없습니다.")
    return text


def _extract_pdf(filename: str, data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - web extra 설치 시 항상 있음
        raise ExtractionError(filename, "PDF 를 읽는 도구가 없습니다.") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionError(
            filename, "PDF 를 읽지 못했습니다. 손상되었거나 암호가 걸린 파일인지 확인해 주세요."
        ) from exc
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception as exc:  # 페이지 하나가 깨져도 나머지를 계속 읽는다
            raise ExtractionError(
                filename, "PDF 일부 페이지를 읽지 못했습니다. 다시 내려받아 올려 주세요."
            ) from exc
    text = "\n".join(parts).strip()
    if not text:
        raise ExtractionError(
            filename, "PDF 에서 글자를 찾지 못했습니다. 스캔 이미지라면 텍스트 파일로 올려 주세요."
        )
    return text


def _extract_docx(filename: str, data: bytes) -> str:
    try:
        import docx
    except ImportError as exc:  # pragma: no cover
        raise ExtractionError(filename, "Word 문서를 읽는 도구가 없습니다.") from exc
    try:
        document = docx.Document(io.BytesIO(data))
    except Exception as exc:
        raise ExtractionError(
            filename, "Word 문서(.docx)를 읽지 못했습니다. 손상된 파일인지 확인해 주세요."
        ) from exc
    parts: list[str] = []
    for paragraph in document.paragraphs:
        if paragraph.text.strip():
            parts.append(paragraph.text)
    # 표 안의 글자도 읽는다
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text.strip():
                    parts.append(cell.text)
    text = "\n".join(parts).strip()
    if not text:
        raise ExtractionError(filename, "Word 문서에서 글자를 찾지 못했습니다.")
    return text


def _extract_hwpx(filename: str, data: bytes) -> str:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ExtractionError(
            filename, "한글 문서(.hwpx)를 읽지 못했습니다. 파일이 손상되었는지 확인해 주세요."
        ) from exc

    # 본문 텍스트는 Contents/ 아래의 XML(hpf 또는 xml)에 있다.
    candidates = [
        name
        for name in archive.namelist()
        if name.startswith("Contents/") and (name.endswith(".hpf") or name.endswith(".xml"))
    ]
    if not candidates:
        raise ExtractionError(filename, "한글 문서(.hwpx)에서 본문을 찾지 못했습니다.")

    parts: list[str] = []
    for name in sorted(candidates):
        try:
            root = ElementTree.fromstring(archive.read(name))
        except Exception as exc:  # XML 이 깨져도 다음 파일을 시도
            continue
        # <hp:t> 등 텍스트 태그의 글자를 모은다 (이름이 't' 로 끝나는 태그).
        chunks = []
        for elem in root.iter():
            tag = elem.tag.rsplit("}", 1)[-1]
            if tag == "t" and elem.text and elem.text.strip():
                chunks.append(elem.text.strip())
        if chunks:
            parts.append(" ".join(chunks))
    text = "\n".join(p for p in parts if p).strip()
    if not text:
        raise ExtractionError(filename, "한글 문서(.hwpx)에서 글자를 찾지 못했습니다.")
    return text


def extract_sources(
    files: list[tuple[str, bytes]],
) -> tuple[list[tuple[str, str]], list[str]]:
    """여러 파일을 읽어 (파일명, 텍스트) 목록과 파일별 경고(한국어)를 돌려준다.

    실패한 파일은 경고로 남기고 나머지 파일은 계속 사용한다. 전체가 실패해도
    과목 이름만으로 초안을 만들 수 있도록 빈 목록과 경고를 돌려준다.
    """
    sources: list[tuple[str, str]] = []
    warnings: list[str] = []
    for filename, data in files:
        try:
            text = extract_text(filename, data)
        except ExtractionError as exc:
            warnings.append(exc.message)
            continue
        sources.append((filename, text))
    return sources, warnings
