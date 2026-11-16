"""백엔드 HTTP API 테스트 (FastAPI TestClient, 네트워크 없음).

스텁 생성기를 주입해 과목 이름만으로 초안을 만들고, PATCH·제안 수락·인계가
교수 편집 내용을 그대로 반영하는지 확인한다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from coursespec.web.app import create_app
from coursespec.web.drafting import stub_payload


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSESPEC_WEB_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.setenv("COURSESPEC_LLM_STUB", "1")
    app = create_app(generate=lambda title, goals, sources: stub_payload(title, goals, sources))
    return TestClient(app)


def _create(client, title, goals="", files=None):
    data = {"title": title, "goals": goals}
    files = files or []
    return client.post("/api/drafts", data=data, files=files)


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_requires_title_in_korean(client):
    response = client.post("/api/drafts", data={"goals": "목표만"})
    assert response.status_code == 422
    assert "과목 이름" in response.json()["message"]


def test_create_with_title_only(client):
    response = _create(client, "AI 에이전트 시대의 교육")
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "AI 에이전트 시대의 교육"
    assert body["outcomes"]
    assert body["weeks"]
    assert body["grading"]
    assert body["id"]
    # 화면에 YAML·패치·도구 이름이 보이지 않는다 (구조화 JSON 만)
    assert "yaml" not in str(body).lower()


def test_create_reflects_ethics_from_file(client):
    response = _create(
        client,
        "AI 윤리 입문",
        goals="윤리",
        files=[("files", ("원고.txt", "이 책의 윤리 장을 다룬다.".encode("utf-8"), "text/plain"))],
    )
    assert response.status_code == 200
    body = response.json()
    assert body["sources_used"] == ["원고.txt"]
    assert any("윤리" in week["title"] for week in body["weeks"])


def test_get_draft(client):
    draft_id = _create(client, "자료구조").json()["id"]
    response = client.get(f"/api/drafts/{draft_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "자료구조"


def test_get_missing_draft_404(client):
    response = client.get("/api/drafts/없는아이디")
    assert response.status_code == 404
    assert "찾지 못했습니다" in response.json()["message"]


def test_patch_reflected_in_handoff(client):
    draft_id = _create(client, "원래 제목").json()["id"]
    patch = {
        "title": "교수가 고친 제목",
        "grading": [{"name": "중간고사", "weight": 40}, {"name": "기말고사", "weight": 60}],
    }
    response = client.patch(f"/api/drafts/{draft_id}", json=patch)
    assert response.status_code == 200
    assert response.json()["title"] == "교수가 고친 제목"

    handoff = client.post(f"/api/drafts/{draft_id}/handoff").json()
    text = handoff["text"]
    assert "교수가 고친 제목" in text
    assert "중간고사: 40%" in text
    assert "기말고사: 60%" in text


def test_suggestion_accept_applies_only_on_accept(client):
    draft_id = _create(client, "AI 윤리 입문", goals="윤리").json()["id"]
    draft = client.get(f"/api/drafts/{draft_id}").json()
    assert draft["suggestions"], "스텁 초안에는 제안이 있어야 한다"
    sid = draft["suggestions"][0]["id"]

    # 수락 전에는 본문이 그대로
    before = client.get(f"/api/drafts/{draft_id}").json()
    assert before["weeks"] == draft["weeks"]

    accepted = client.post(f"/api/drafts/{draft_id}/suggestions/{sid}/accept").json()
    assert any(s["status"] == "accepted" for s in accepted["suggestions"])

    # 첫 제안은 주차 제목을 고치는 제안이므로 본문이 바뀌어야 한다
    assert accepted["weeks"] != before["weeks"]


def test_suggestion_skip_does_not_change_body(client):
    draft_id = _create(client, "AI 윤리 입문", goals="윤리").json()["id"]
    draft = client.get(f"/api/drafts/{draft_id}").json()
    sid = draft["suggestions"][0]["id"]

    skipped = client.post(f"/api/drafts/{draft_id}/suggestions/{sid}/skip").json()
    assert any(s["status"] == "skipped" for s in skipped["suggestions"])
    assert skipped["weeks"] == draft["weeks"]
    assert skipped["grading"] == draft["grading"]


def test_regenerate_resets_edits(client):
    draft_id = _create(client, "원래 제목").json()["id"]
    client.patch(f"/api/drafts/{draft_id}", json={"title": "편집한 제목"})
    response = client.post(f"/api/drafts/{draft_id}/regenerate")
    assert response.status_code == 200
    assert response.json()["title"] == "원래 제목"


def test_no_model_config_returns_friendly_503(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSESPEC_WEB_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.delenv("COURSESPEC_LLM_STUB", raising=False)
    monkeypatch.delenv("COURSESPEC_LLM_KEY_PATH", raising=False)
    monkeypatch.delenv("COURSESPEC_LLM_URL_PATH", raising=False)
    app = create_app()
    test_client = TestClient(app)
    response = _create(test_client, "과목")
    assert response.status_code == 503
    assert "모델 연결 정보가 없습니다" in response.json()["message"]
