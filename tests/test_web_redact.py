"""로그 적색 테스트: 토큰·Bearer·API 키, 쿼리스트림 key, 자격증명이 박힌 URL 이
로그 문자열에 남지 않는지 확인한다."""

from __future__ import annotations

from coursespec.web.redact import redact


def test_redacts_bearer_token():
    out = redact("Authorization: Bearer abcDEF1234567890_xyz")
    assert "abcDEF1234567890_xyz" not in out
    assert "[redacted]" in out


def test_redacts_sk_key():
    out = redact("key는 sk-abcdefghijklmnopqrstuvwxyz123456 입니다")
    assert "sk-abcdefghijklmnopqrstuvwxyz123456" not in out
    assert "sk-[redacted]" in out


def test_redacts_key_value_assignment():
    out = redact("api_key=SuperSecretValue123")
    assert "SuperSecretValue123" not in out


def test_redacts_query_string_key():
    out = redact("https://example.test/path?key=hunter2&other=1")
    assert "hunter2" not in out
    assert "key=[redacted]" in out


def test_redacts_userinfo_in_url():
    out = redact("https://user:hunter2@example.test/path")
    assert "hunter2" not in out


def test_redact_keeps_plain_text():
    out = redact("교수님이 초안을 확인했습니다.")
    assert out == "교수님이 초안을 확인했습니다."


def test_redact_empty():
    assert redact("") == ""
