"""로그 적색(redaction) 처리.

토큰·Bearer·API 키, 쿼리스트링의 key, 실호스트처럼 보이는 값이 로그에 남지 않도록
로그 메시지에 적용한다. 비밀값은 값 자체를 다루지 않고, 오직 로그 문자열에서 감춘다.
"""

from __future__ import annotations

import re

# 순서가 중요하다: 긴 패턴(예: Authorization 헤더)을 먼저 매칭한다.
_PATTERNS: list[tuple[str, str]] = [
    # "Authorization: Bearer <token>" / "Bearer <token>"
    (r"(?i)\bBearer\s+[A-Za-z0-9._~+/=\-]{8,}", "Bearer [redacted]"),
    (r"(?i)Authorization\s*[:=]\s*[^\s,;]+", "Authorization: [redacted]"),
    # OpenAI 호환 키 (sk-...), 일반 API 키/토큰/비밀/패스워드 대입
    (r"(?i)\bsk-[A-Za-z0-9\-_]{10,}", "sk-[redacted]"),
    (r"(?i)\b(api[_-]?key|apikey|token|secret|password|passwd|pwd)\b\s*[:=]\s*[^\s,;&]+", r"\1=[redacted]"),
    # "key=..." 형태 쿼리스트링 값
    (r"(?i)([?&](?:api[_-]?key|key|token|secret|access_token)=)[^&\s]+", r"\1[redacted]"),
]

# 실호스트/URL 처럼 보이는 값은 일부러 넓게 가리지 않는다. 목업·문서와 충돌하기 쉽기 때문에
# 위의 명시적 비밀 패턴(키·토큰·Bearer)만 적색하고, 호스트는 코드에 실주소를 넣지 않는
# 정책으로 막는다. 아래는 "user:pass@host" 와 같이 자격증명이 박힌 URL만 감춘다.
_HOST_PATTERNS: list[tuple[str, str]] = [
    (r"(?i)(https?://)[^/\s:@]+:[^/\s:@]+@", r"\1[redacted]@"),
]


def redact(text: str) -> str:
    """로그·오류 문자열에서 비밀값 패턴을 감춘다. 평문에는 영향이 없다."""
    if not text:
        return text
    out = text
    for pattern, repl in _PATTERNS:
        out = re.sub(pattern, repl, out)
    for pattern, repl in _HOST_PATTERNS:
        out = re.sub(pattern, repl, out)
    return out
