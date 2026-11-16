"""프롬프트·스텁 픽스처 테스트.

과목+목표만(파일 없음)으로 초안이 나오고, 추출문에 '윤리' 같은 구절이 있으면
초안 주차·학습목표·제안에 그 흔적이 남는다. 네트워크는 호출하지 않는다.
"""

from __future__ import annotations

import os

import pytest

from coursespec.web.drafting import MODEL_MISSING_MESSAGE, build_messages, generate_draft, stub_payload
from coursespec.web.errors import DraftError


def test_build_messages_contains_inputs():
    messages = build_messages("AI 윤리 입문", "윤리 원칙을 가르친다", [("원고.txt", "개인정보 보호")])
    user = messages[1]["content"]
    assert "AI 윤리 입문" in user
    assert "윤리 원칙을 가르친다" in user
    assert "원고.txt" in user
    assert "개인정보 보호" in user


def test_stub_with_title_and_goals_only():
    payload = stub_payload("AI 에이전트 시대의 교육", "교사 대상 4주 과정", [])
    assert payload["title"] == "AI 에이전트 시대의 교육"
    assert payload["intro"]
    assert len(payload["outcomes"]) == 3
    assert len(payload["weeks"]) == 4
    assert sum(g["weight"] for g in payload["grading"]) == 100
    assert payload["suggestions"]


def test_stub_reflects_ethics_in_sources():
    payload = stub_payload(
        "AI 윤리 입문",
        "윤리를 가르친다",
        [("원고.txt", "이 책의 윤리 장은 4주차에 다룬다.")],
    )
    assert any("윤리" in week["title"] for week in payload["weeks"])
    assert any("윤리" in outcome for outcome in payload["outcomes"])
    assert any("윤리" in s["text"] for s in payload["suggestions"])


def test_generate_draft_uses_stub_env(monkeypatch):
    monkeypatch.setenv("COURSESPEC_LLM_STUB", "1")
    monkeypatch.delenv("COURSESPEC_LLM_KEY_PATH", raising=False)
    payload = generate_draft("자료구조", "알고리즘 이해", [])
    assert payload["title"] == "자료구조"
    assert payload["weeks"]


def test_generate_draft_injected_callable():
    def fake_call(title, goals, sources):
        return {
            "title": title,
            "intro": "테스트 소개",
            "outcomes": ["목표 1"],
            "weeks": [{"title": "1주", "summary": "요약"}],
            "grading": [{"name": "과제", "weight": 100}],
            "suggestions": [],
        }

    payload = generate_draft("과정", "목표", [], call=fake_call)
    assert payload["title"] == "과정"
    assert payload["outcomes"] == ["목표 1"]


def test_generate_draft_without_key_or_stub_raises_friendly(monkeypatch):
    monkeypatch.delenv("COURSESPEC_LLM_STUB", raising=False)
    monkeypatch.delenv("COURSESPEC_LLM_KEY_PATH", raising=False)
    monkeypatch.delenv("COURSESPEC_LLM_URL_PATH", raising=False)
    with pytest.raises(DraftError) as excinfo:
        generate_draft("과정", "", [])
    assert excinfo.value.message == MODEL_MISSING_MESSAGE
    assert "모델 연결 정보가 없습니다" in excinfo.value.message
