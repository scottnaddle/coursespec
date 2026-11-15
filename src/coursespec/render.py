"""본문 형식 변환."""

from __future__ import annotations

import markdown as _md


def to_html(text: str | None, fmt: str = "markdown") -> str:
    if not text:
        return ""
    if fmt == "html":
        return text
    return _md.markdown(text, extensions=["extra", "sane_lists"])
