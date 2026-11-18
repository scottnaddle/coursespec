"""M2 과정 지도 — 설계서 생성(스텁) 테스트.

스텁 설계 에이전트는 네트워크 없이 초안 필드를 그대로 반영한 CourseSpec 0.2 설계서를
만든다. 결과는 스키마 오류 0, 린트 오류 0 이고, 교수가 고친 제목·주차 제목·평가 비중이
그대로 반영된다. 모델 연결 정보가 없으면 쉬운 한국어 503 안내를 돌려준다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from coursespec.lint import lint
from coursespec.spec import from_data
from coursespec.web.app import create_app
from coursespec.web.design import generate_design, stub_design
from coursespec.web.drafting import stub_payload
from coursespec.web.errors import DraftError


def test_stub_design_passes_schema_and_lint_with_zero_errors():
    draft = stub_payload("AI 에이전트 시대의 교육", "교사 대상 4주 과정", [])
    design = stub_design("", draft)
    spec = from_data(design)
    errors = [f for f in lint(spec) if f.is_error]
    assert errors == []


def test_stub_design_reflects_professor_edits():
    draft = stub_payload("AI 에이전스 시대의 교육", "4주 과정", [])
    draft["title"] = "AI 에이전트 시대의 교육(심화)"
    draft["weeks"][1]["title"] = "수업 속 에이전트 시나리오"
    draft["grading"][0]["weight"] = 30
    design = stub_design("", draft)

    assert design["title"] == "AI 에이전트 시대의 교육(심화)"
    assert design["units"][1]["title"] == "2주차 — 수업 속 에이전트 시나리오"
    assert design["grading"]["categories"][0]["weight"] == 30


def test_stub_design_handles_empty_weeks_and_outcomes():
    draft = stub_payload("미니 과정", "1주 과정", [])
    draft["weeks"] = []
    draft["outcomes"] = []
    design = stub_design("", draft)
    spec = from_data(design)
    assert [f for f in lint(spec) if f.is_error] == []
    assert len(design["units"]) == 1


def test_generate_design_uses_stub_env(monkeypatch):
    monkeypatch.setenv("COURSESPEC_LLM_STUB", "1")
    monkeypatch.delenv("COURSESPEC_LLM_KEY_PATH", raising=False)
    draft = stub_payload("자료구조", "알고리즘 이해", [])
    design = generate_design(draft)
    assert design["title"] == "자료구조"
    assert design["units"]


def test_generate_design_injected_callable():
    def fake_call(handoff_text, draft):
        return stub_design(handoff_text, draft)

    draft = stub_payload("운영체제", "", [])
    design = generate_design(draft, call=fake_call)
    assert design["units"]


def test_generate_design_without_config_gives_friendly_korean(monkeypatch):
    monkeypatch.delenv("COURSESPEC_LLM_STUB", raising=False)
    monkeypatch.delenv("COURSESPEC_LLM_KEY_PATH", raising=False)
    monkeypatch.delenv("COURSESPEC_LLM_URL_PATH", raising=False)
    draft = stub_payload("네트워크", "", [])
    with pytest.raises(DraftError) as excinfo:
        generate_design(draft)
    assert "모델 연결 정보가 없습니다" in excinfo.value.message


def test_llm_url_must_be_https(tmp_path, monkeypatch):
    """실모델 주소는 https 만 허용한다. 값(주소·키)은 메시지에 남기지 않는다."""
    key_file = tmp_path / "key.txt"
    key_file.write_text("test-key", encoding="utf-8")
    url_file = tmp_path / "url.txt"
    url_file.write_text("http://example.invalid/v1", encoding="utf-8")
    monkeypatch.delenv("COURSESPEC_LLM_STUB", raising=False)
    monkeypatch.setenv("COURSESPEC_LLM_KEY_PATH", str(key_file))
    monkeypatch.setenv("COURSESPEC_LLM_URL_PATH", str(url_file))
    draft = stub_payload("보안 연결", "", [])
    with pytest.raises(DraftError) as excinfo:
        generate_design(draft)
    assert "주소가 올바르지 않습니다" in excinfo.value.message
    assert "http" not in excinfo.value.message


def test_design_endpoint_503_korean_when_model_missing(tmp_path, monkeypatch):
    """모델 연결 정보가 없으면 설계서 생성은 저장 없이 쉬운 한국어 503 안내를 돌려준다."""
    monkeypatch.setenv("COURSESPEC_WEB_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.setenv("COURSESPEC_LLM_STUB", "1")
    client = TestClient(create_app())
    created = client.post("/api/drafts", data={"title": "임시 과정"}).json()

    monkeypatch.delenv("COURSESPEC_LLM_STUB", raising=False)
    monkeypatch.delenv("COURSESPEC_LLM_KEY_PATH", raising=False)
    monkeypatch.delenv("COURSESPEC_LLM_URL_PATH", raising=False)
    response = client.post(f"/api/drafts/{created['id']}/design")
    assert response.status_code == 503
    assert "모델 연결 정보가 없습니다" in response.json()["message"]
    # 응답에 남은 흔적이 없다 (경로 비밀 이름조차 노출하지 않는다).
    assert "COURSESPEC_LLM" not in response.text
    # 저장된 설계서도 없다.
    assert not list((tmp_path / "workspace").rglob("*.coursespec.yaml"))
