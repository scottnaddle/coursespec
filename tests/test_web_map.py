"""M2 과정 지도 — 화면 모델·편집·수정 요청·확정 API 테스트.

- 예시 설계서가 YAML 없이 화면 모델로 완전히 읽힌다. 린트 0 예시에서는 notices 가 비어
  있다 (허위 경고 배너 없음). 경고를 만든 설계서에는 쉬운 문장 notice 가 생기고 코드가 안 보인다.
- 편집·수정 요청은 검증된 JSON Patch 로만 적용되며, 검증 실패 시 파일 바이트가 불변이다.
- 예시 원본(examples/)은 모든 동작 뒤에도 바이트 그대로다.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from coursespec.patch import patch_file
from coursespec.web.app import create_app

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "ai-agent-education.coursespec.yaml"

EXAMPLE_HASH = hashlib.sha256(EXAMPLE.read_bytes()).hexdigest()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSESPEC_WEB_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.setenv("COURSESPEC_LLM_STUB", "1")
    return TestClient(create_app())


@pytest.fixture
def example_id(client):
    response = client.post("/api/designs/example")
    assert response.status_code == 200
    return response.json()["design_id"]


def _design_path(design_id) -> Path:
    from coursespec.web.storage import design_path

    return design_path(design_id)


# --- 예시 화면 모델 -----------------------------------------------------------

def test_example_map_covers_everything_without_yaml_traces(client, example_id):
    body = client.get(f"/api/designs/{example_id}").json()
    raw = EXAMPLE.read_text("utf-8")
    data = yaml.safe_load(raw)

    assert body["summary"]["unit_count"] == len(data["units"])
    assert body["summary"]["outcome_count"] == len(data["outcomes"])
    assert "설계 과제 60%" in body["summary"]["grading"]
    assert body["summary"]["max_per_unit_label"] == "4시간"

    for unit in data["units"]:
        found = next(u for u in body["units"] if u["id"] == unit["id"])
        for item in unit.get("items", []):
            assert any(i["title"] == item["title"] for i in found["items"]), item["title"]
    for outcome in data["outcomes"]:
        assert any(o["statement"] == outcome["statement"] for o in body["outcomes"])

    # 화면 모델에 YAML·패치 흔적이 없다
    import json

    text = json.dumps(body, ensure_ascii=False)
    assert "coursespec:" not in text
    assert '"op"' not in text
    assert "/units/" not in text


def test_example_map_has_no_false_notices(client, example_id):
    body = client.get(f"/api/designs/{example_id}").json()
    assert body["notices"] == []
    assert body["can_confirm"] is True


def test_warning_notice_is_easy_korean_without_code(client, example_id):
    """가중치 합을 100이 아니게 만들면 쉬운 문장 경고가 생기고 코드(W1xx)는 안 보인다."""
    path = _design_path(example_id)
    patch_file(path, [{"op": "replace", "path": "/grading/categories/0/weight", "value": 30}])

    body = client.get(f"/api/designs/{example_id}").json()
    warnings = [n for n in body["notices"] if n["severity"] == "warning"]
    assert warnings, body["notices"]
    assert any("평가 비중" in w["message"] for w in warnings)
    assert all("W1" not in w["message"] and "W1" not in w["where"] for w in warnings)
    assert warnings[0]["where"] == "평가 비중"


def test_example_original_unchanged_after_opening(client, example_id):
    assert hashlib.sha256(EXAMPLE.read_bytes()).hexdigest() == EXAMPLE_HASH


# --- 편집 흐름 ----------------------------------------------------------------

def test_edit_unit_and_item_fields(client, example_id):
    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={
            "actions": [
                {"action": "update_unit", "unit_id": "w2", "title": "수업 속 에이전트 시나리오(심화)"},
                {"action": "update_item", "unit_id": "w1", "item_id": "w1-quiz",
                 "minutes": 20, "due_day": 9},
            ]
        },
    )
    assert response.status_code == 200, response.text
    unit = next(u for u in response.json()["units"] if u["id"] == "w2")
    assert unit["title"] == "수업 속 에이전트 시나리오(심화)"
    quiz = next(i for i in response.json()["units"][0]["items"] if i["id"] == "w1-quiz")
    assert quiz["minutes"] == 20 and quiz["due_label"] == "9일차 마감"

    data = yaml.safe_load(_design_path(example_id).read_text("utf-8"))
    assert data["units"][1]["title"] == "수업 속 에이전트 시나리오(심화)"
    quiz_data = next(i for i in data["units"][0]["items"] if i["id"] == "w1-quiz")
    assert quiz_data["estimated_minutes"] == 20 and quiz_data["due_day"] == 9


def test_edit_preserves_yaml_comments(client, example_id):
    path = _design_path(example_id)
    before = path.read_text("utf-8")
    assert "# 자료 매니페스트" in before

    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [{"action": "update_unit", "unit_id": "w1", "summary": "바꾼 요약"}]},
    )
    assert response.status_code == 200
    after = path.read_text("utf-8")
    assert "# 자료 매니페스트" in after  # 주석 보존
    assert "바꾼 요약" in after


def test_add_remove_move_items(client, example_id):
    # 추가
    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [{"action": "add_item", "unit_id": "w3", "kind": "토론",
                           "title": "시나리오 나누기", "minutes": 25}]},
    )
    assert response.status_code == 200, response.text
    data = yaml.safe_load(_design_path(example_id).read_text("utf-8"))
    w3 = data["units"][2]
    new_item = next(i for i in w3["items"] if i["title"] == "시나리오 나누기")
    assert new_item["type"] == "discussion"

    # 다른 주차로 이동
    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [{"action": "move_item", "unit_id": "w3", "item_id": new_item["id"],
                           "to_unit_id": "w4"}]},
    )
    assert response.status_code == 200, response.text
    data = yaml.safe_load(_design_path(example_id).read_text("utf-8"))
    assert any(i["title"] == "시나리오 나누기" for i in data["units"][3]["items"])
    assert not any(i["title"] == "시나리오 나누기" for i in data["units"][2]["items"])

    # 삭제
    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [{"action": "remove_item", "unit_id": "w4", "item_id": new_item["id"]}]},
    )
    assert response.status_code == 200, response.text
    data = yaml.safe_load(_design_path(example_id).read_text("utf-8"))
    assert not any(i["title"] == "시나리오 나누기" for i in data["units"][3]["items"])


def test_removing_required_item_fails_and_file_is_unchanged(client, example_id):
    path = _design_path(example_id)
    before = path.read_bytes()
    # w1-quiz 는 2주차 단원의 선수조건(requires)으로 쓰인다.
    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [{"action": "remove_item", "unit_id": "w1", "item_id": "w1-quiz"}]},
    )
    assert response.status_code == 409
    assert "문제" in response.json()["message"]
    assert path.read_bytes() == before


def test_moving_to_unknown_unit_fails_and_file_is_unchanged(client, example_id):
    path = _design_path(example_id)
    before = path.read_bytes()
    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [{"action": "move_item", "unit_id": "w1", "item_id": "w1-notes",
                           "to_unit_id": "w99"}]},
    )
    assert response.status_code == 404
    assert "주차" in response.json()["message"]
    assert path.read_bytes() == before


# --- 수정 요청 ----------------------------------------------------------------

def test_change_request_preview_apply(client, example_id):
    path = _design_path(example_id)
    original_title = yaml.safe_load(path.read_text("utf-8"))["units"][1]["title"]
    preview = client.post(
        f"/api/designs/{example_id}/change-requests",
        json={"text": "2주차 제목을 '수업 속 에이전트 시나리오'로 바꿔 주세요"},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["summary"] == ["2주차 제목을 '수업 속 에이전트 시나리오'(으)로 바꿉니다."]
    # 미리 보기만 하고 아직 파일은 안 바뀐다
    assert yaml.safe_load(path.read_text("utf-8"))["units"][1]["title"] == original_title


def test_change_request_apply_reflects(client, example_id):
    preview = client.post(
        f"/api/designs/{example_id}/change-requests",
        json={"text": "2주차 제목을 '수업 속 에이전트 시나리오'로 바꿔 주세요"},
    ).json()
    applied = client.post(
        f"/api/designs/{example_id}/change-requests/{preview['request_id']}/apply"
    )
    assert applied.status_code == 200, applied.text
    unit = next(u for u in applied.json()["units"] if u["id"] == "w2")
    assert unit["title"] == "수업 속 에이전트 시나리오"
    data = yaml.safe_load(_design_path(example_id).read_text("utf-8"))
    assert data["units"][1]["title"] == "수업 속 에이전트 시나리오"


def test_change_request_discard_keeps_file(client, example_id):
    path = _design_path(example_id)
    before = path.read_bytes()
    preview = client.post(
        f"/api/designs/{example_id}/change-requests",
        json={"text": "3주차에 토론 '보충 토론' 추가"},
    ).json()
    discarded = client.post(
        f"/api/designs/{example_id}/change-requests/{preview['request_id']}/discard"
    )
    assert discarded.status_code == 200
    assert path.read_bytes() == before
    # 취소한 뒤 적용은 못 한다
    late = client.post(f"/api/designs/{example_id}/change-requests/{preview['request_id']}/apply")
    assert late.status_code == 404
    assert "찾지 못했습니다" in late.json()["message"]


def test_change_request_apply_fails_after_design_changed(client, example_id):
    path = _design_path(example_id)
    preview = client.post(
        f"/api/designs/{example_id}/change-requests",
        json={"text": "2주차 제목을 '새 제목'로 바꿔 주세요"},
    ).json()
    # 그 사이에 다른 편집이 들어온다
    edit = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [{"action": "update_unit", "unit_id": "w2", "title": "딴 제목"}]},
    )
    assert edit.status_code == 200
    applied = client.post(
        f"/api/designs/{example_id}/change-requests/{preview['request_id']}/apply"
    )
    assert applied.status_code == 409
    assert "바뀌" in applied.json()["message"]
    data = yaml.safe_load(path.read_text("utf-8"))
    assert data["units"][1]["title"] == "딴 제목"


def test_change_request_unrecognized_sentence_gets_easy_guidance(client, example_id):
    response = client.post(
        f"/api/designs/{example_id}/change-requests",
        json={"text": "분위기를 좀 더 따뜻하게 해 주세요"},
    )
    assert response.status_code == 400
    assert "이해하지 못했어요" in response.json()["message"]


def test_change_request_patch_is_not_exposed(client, example_id):
    preview = client.post(
        f"/api/designs/{example_id}/change-requests",
        json={"text": "3주차에 퀴즈 추가"},
    )
    text = preview.text
    assert '"op"' not in text
    assert "/units/" not in text


# --- 확정 --------------------------------------------------------------------

def test_confirm_clean_design(client, example_id):
    response = client.post(f"/api/designs/{example_id}/confirm")
    assert response.status_code == 200
    assert response.json()["confirmed"] is True
    body = client.get(f"/api/designs/{example_id}").json()
    assert body["confirmed"] is True


def test_confirm_rejected_when_errors_exist(client, example_id):
    # 존재하지 않는 학습목표를 참조하는 활동을 직접 끼워 넣어 린트 오류를 낸다.
    path = _design_path(example_id)
    data = yaml.safe_load(path.read_text("utf-8"))
    data["units"][0]["items"].append(
        {"id": "w1-broken", "type": "page", "title": "깨진 활동",
         "outcomes": ["lo99"], "content": "내용", "completion": {"mode": "view"}}
    )
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    response = client.post(f"/api/designs/{example_id}/confirm")
    assert response.status_code == 409
    assert "오류" in response.json()["message"]
    body = client.get(f"/api/designs/{example_id}").json()
    assert body["can_confirm"] is False
    assert any(n["severity"] == "error" for n in body["notices"])
