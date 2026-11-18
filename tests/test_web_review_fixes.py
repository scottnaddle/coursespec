"""M2 리뷰 반영 회귀 테스트.

블로커 4건(없는 키 편집 409, 제목+마감일 묶음 409, 다중 동작 순번 어긋남/id 중복,
린트 원문·원시 id 누출)과 정확성 이슈(오래된 수정 요청 적용, 스텁 검증 실패 500,
확정 해제, 경로 조작 id, 생성 결과 저장 전 미검증)를 고정한다.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient

from coursespec.lint import Finding
from coursespec.spec import from_data
from coursespec.web.app import create_app
from coursespec.web.course_map import (
    _FRIENDLY_MESSAGES,
    _GENERIC_NOTICE,
    _friendly_message,
    _where_label,
)
from coursespec.web.storage import design_path, load_requests

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "ai-agent-education.coursespec.yaml"
EXAMPLE_HASH = hashlib.sha256(EXAMPLE.read_bytes()).hexdigest()

EXPECTED_LINT_CODES = {
    "E001", "E002", "E003", "E004", "E005", "E006", "E007", "E008", "E009",
    "E010", "E011", "E012", "E013", "E014", "E015", "E016", "E017",
    "W101", "W102", "W103", "W104", "W105", "W106", "W107", "W108", "W109",
    "W110", "W111", "W112", "W113", "W115",
}

RAW_LEAK = "E001 requires 'w2-quiz' grading rights.license uses: learner lecture.prompt multiple: true pass_grade"


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


def _data(design_id) -> dict:
    return yaml.safe_load(design_path(design_id).read_text("utf-8"))


def _unit(data, unit_id):
    return next(u for u in data["units"] if u["id"] == unit_id)


# --- 블로커 1: 없는 키(요약) 편집 ------------------------------------------------

def test_summary_only_edit_on_unit_without_summary_key(client, example_id):
    """예시 2주차에는 summary 키가 없다. 요약만 본낸 프론트 요청이 통과하고,
    제목(“N주차 —” 접두어 포함)은 그대로여야 한다."""
    before = _data(example_id)
    assert "summary" not in _unit(before, "w2")

    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [{"action": "update_unit", "unit_id": "w2", "summary": "새 요약"}]},
    )
    assert response.status_code == 200, response.text

    after = _data(example_id)
    assert _unit(after, "w2")["summary"] == "새 요약"
    assert _unit(after, "w2")["title"] == _unit(before, "w2")["title"]

    unit = next(u for u in response.json()["units"] if u["id"] == "w2")
    assert unit["summary"] == "새 요약"
    # 화면 모델의 제목은 원래대로 “N주차 —” 접두어가 뗀 형태다(파일 제목은 그대로).
    assert unit["title"] == "수업 속 에이전트 시나리오"


def test_summary_edit_with_same_value_is_skipped(client, example_id):
    """값이 바뀌지 않은 필드는 op 를 만들지 않는다(제목 그대로 본낸 경우에도 안전)."""
    before = _data(example_id)
    title = _unit(before, "w2")["title"]
    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [{"action": "update_unit", "unit_id": "w2",
                           "title": title, "summary": "요약만 고침"}]},
    )
    assert response.status_code == 200, response.text
    after = _data(example_id)
    assert _unit(after, "w2")["title"] == title
    assert _unit(after, "w2")["summary"] == "요약만 고침"


# --- 블로커 2: 제목 + 마감일 묶음 ------------------------------------------------

def test_item_title_and_due_day_in_one_action(client, example_id):
    """활동 제목과 마감일을 한 동작에 본낸다(프론트가 항상 그렇게 본낸다)."""
    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [{"action": "update_item", "unit_id": "w2",
                           "item_id": "w2-scenario", "title": "과제 1(개정)",
                           "due_day": 16}]},
    )
    assert response.status_code == 200, response.text
    item = next(i for i in _unit(_data(example_id), "w2")["items"] if i["id"] == "w2-scenario")
    assert item["title"] == "과제 1(개정)" and item["due_day"] == 16


def test_due_day_only_edit_on_item_with_due(client, example_id):
    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [{"action": "update_item", "unit_id": "w2",
                           "item_id": "w2-scenario", "due_day": 15}]},
    )
    assert response.status_code == 200, response.text
    item = next(i for i in _unit(_data(example_id), "w2")["items"] if i["id"] == "w2-scenario")
    assert item["due_day"] == 15


def test_due_day_cleared_with_null(client, example_id):
    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [{"action": "update_item", "unit_id": "w2",
                           "item_id": "w2-scenario", "due_day": None}]},
    )
    assert response.status_code == 200, response.text
    item = next(i for i in _unit(_data(example_id), "w2")["items"] if i["id"] == "w2-scenario")
    assert "due_day" not in item


# --- 블로커 3: 한 번에 여러 동작 -------------------------------------------------

def test_remove_then_update_later_item_in_one_batch(client, example_id):
    """같은 주차에서 앞 활동을 빼고 뒤 활동을 고치는 묶음: 순번이 어긋나지 않고
    정확한 활동이 바뀐다."""
    before = _unit(_data(example_id), "w1")
    target = before["items"][1]  # w1-notes (w1-reading 은 w1-quiz 의 선수조건이라 못 뺀다)
    removed_id = before["items"][-1]["id"]  # w1-forum
    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [
            {"action": "remove_item", "unit_id": "w1", "item_id": removed_id},
            {"action": "update_item", "unit_id": "w1", "item_id": target["id"],
             "minutes": 99},
        ]},
    )
    assert response.status_code == 200, response.text
    items = _unit(_data(example_id), "w1")["items"]
    assert all(i["id"] != removed_id for i in items)
    updated = next(i for i in items if i["id"] == target["id"])
    assert updated["estimated_minutes"] == 99
    # 다른 활동의 분은 그대로다(순번이 밀려 엉뚱한 활동이 바뀌지 않았다)
    untouched = next(i for i in items if i["id"] == "w1-quiz")
    assert untouched["estimated_minutes"] != 99


def test_move_then_update_in_one_batch(client, example_id):
    before = _unit(_data(example_id), "w1")
    mover = before["items"][-1]  # w1-forum (마감일 없음 — 옮겨도 린트 오류가 안 난다)
    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [
            {"action": "move_item", "unit_id": "w1", "item_id": mover["id"],
             "to_unit_id": "w2"},
            {"action": "update_item", "unit_id": "w2", "item_id": mover["id"],
             "title": "옮겨온 활동(개정)"},
        ]},
    )
    assert response.status_code == 200, response.text
    w2 = _unit(_data(example_id), "w2")
    moved = next(i for i in w2["items"] if i["id"] == mover["id"])
    assert moved["title"] == "옮겨온 활동(개정)"


def test_add_same_kind_twice_in_one_batch_gets_unique_ids(client, example_id):
    """같은 유형 활동을 한 번에 두 개 추가해도 id 가 겹치지 않는다."""
    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [
            {"action": "add_item", "unit_id": "w3", "kind": "토론", "title": "첫 토론", "minutes": 15},
            {"action": "add_item", "unit_id": "w3", "kind": "토론", "title": "둘째 토론", "minutes": 20},
        ]},
    )
    assert response.status_code == 200, response.text
    added = [i for i in _unit(_data(example_id), "w3")["items"] if i["title"] in ("첫 토론", "둘째 토론")]
    assert len(added) == 2
    assert len({i["id"] for i in added}) == 2


def test_file_kind_addition_is_not_supported(client, example_id):
    """자료(파일) 활동은 가짜 경로 없이 만들 수 없어서 지원하지 않는다."""
    response = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [{"action": "add_item", "unit_id": "w3", "kind": "자료",
                           "title": "자료 활동", "minutes": 10}]},
    )
    assert response.status_code == 422


# --- 블로커 4: 린트 원문·코드·원시 id 누출 금지 ------------------------------------

def test_every_lint_code_maps_to_easy_korean_without_leak():
    """모든 린트 코드(E***/W***)에 쉬운 한국어 문장이 있고, 원문/코드/스펙 키/원시
    id/영문이 새어 나가지 않는다. 사전에 없는 코드는 일반 문장으로 돌린다."""
    spec = from_data(yaml.safe_load(EXAMPLE.read_text("utf-8")))
    assert set(_FRIENDLY_MESSAGES) == EXPECTED_LINT_CODES

    for code in sorted(EXPECTED_LINT_CODES | {"W999", "E099"}):
        finding = Finding(code, "w2-quiz", RAW_LEAK)
        message = _friendly_message(finding)
        assert message != RAW_LEAK
        if code in EXPECTED_LINT_CODES:
            assert message != _GENERIC_NOTICE
        else:
            assert message == _GENERIC_NOTICE  # 매핑 없는 코드는 일반 문장
        assert not re.search(r"[EW]\d{3}", message)
        assert not re.search(r"[A-Za-z]", message), message
        assert "w2-quiz" not in message

        where = _where_label(finding, spec)
        assert "w2-quiz" not in where
        assert not re.search(r"[EW]\d{3}", where)
        assert not re.search(r"[A-Za-z]", where), where


def test_real_lint_findings_never_leak_raw_text(client, example_id):
    """실제 린트가 잡아 낸 오류/경고들도 화면 모델에 원문·id·스펙 키가 나가지 않는다."""
    data = _data(example_id)
    w1 = _unit(data, "w1")
    # E001: id 중복
    w1["items"][1]["id"] = w1["items"][0]["id"]
    # E002: 없는 학습목표 참조
    w1["items"][0]["outcomes"] = ["lo1", "lo404"]
    # E003: 없는 선수조건
    _unit(data, "w2")["requires"] = ["no-such-activity"]
    # E005: 없는 평가 항목
    for item in _unit(data, "w2")["items"]:
        if "grading" in item:
            item["grading"]["category"] = "no-such-category"
            break
    # E007: 마감이 공개보다 이른 활동
    early = w1["items"][0]
    early["opens_day"] = 8
    early["due_day"] = 3
    # W104: 비중 합 깨기
    data["grading"]["categories"][0]["weight"] = 10
    # W107: 문항 없는 퀴즈
    for item in w1["items"]:
        if item.get("type") == "quiz":
            item.pop("questions", None)
            break
    # W109: 카테고리 없는 평가 활동
    data["units"][3]["items"].append(
        {"id": "w4-extra-quiz", "type": "quiz", "title": "추가 퀴즈",
         "estimated_minutes": 10, "grading": {"max": 10},
         "questions": [{"type": "truefalse", "text": "내용", "answer": True}]}
    )
    # W112: 이용 권한 없는 자료
    data.setdefault("materials", []).append(
        {"id": "m-leak-check", "title": "권한 미확인 자료", "uses": ["learner"],
         "source": "materials/leak-check.pdf"}
    )
    design_path(example_id).write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    body = client.get(f"/api/designs/{example_id}").json()
    assert body["notices"], "오류/경고를 만들었는데 notices 가 비어 있다"
    blob = json.dumps(body["notices"], ensure_ascii=False)
    for finding_text in ("requires", "grading", "rights.license", "uses: learner",
                         "lecture.prompt", "multiple: true", "pass_grade"):
        assert finding_text not in blob, finding_text
    assert not re.search(r"[EW]\d{3}", blob)
    assert not re.search(r"\bw\d-(quiz|reading|notes|forum)\b", blob)
    assert body["can_confirm"] is False
    # 원본 예시는 그대로다
    assert hashlib.sha256(EXAMPLE.read_bytes()).hexdigest() == EXAMPLE_HASH


# --- 수정 요청: 해시 보호·스텁 검증 실패·id test ---------------------------------

def test_stored_request_has_id_test_for_add_and_remove(client, example_id):
    add = client.post(
        f"/api/designs/{example_id}/change-requests",
        json={"text": "3주차에 토론 '보충 토론' 추가"},
    ).json()
    remove = client.post(
        f"/api/designs/{example_id}/change-requests",
        json={"text": "1주차 '강의 노트 내려받기'를 삭제"},
    )
    assert remove.status_code == 200, remove.text
    remove = remove.json()

    requests = {r["request_id"]: r for r in load_requests(example_id)}
    for request in (requests[add["request_id"]], requests[remove["request_id"]]):
        ops = request["ops"]
        tests = [o for o in ops if o["op"] == "test"]
        assert tests and all(t["path"].endswith("/id") for t in tests)
    # 제목 변경 요청도 id 확인 test 가 있다
    title = client.post(
        f"/api/designs/{example_id}/change-requests",
        json={"text": "2주차 제목을 '새 제목'로 바꿔 주세요"},
    ).json()
    requests = {r["request_id"]: r for r in load_requests(example_id)}
    ops = requests[title["request_id"]]["ops"]
    assert any(o["op"] == "test" and o["path"] == "/units/1/id" for o in ops)


def test_stale_remove_request_is_blocked_by_hash(client, example_id):
    """삭제 요청을 만든 뒤 설계서가 바뀌면, 엉뚱한 활동을 지우는 대신 409 로 막는다."""
    preview = client.post(
        f"/api/designs/{example_id}/change-requests",
        json={"text": "1주차 '자기소개와 AI 활용 경험 나누기'를 삭제"},
    ).json()
    # 그 사이 다른 편집
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
    data = _data(example_id)
    assert any(i["title"] == "자기소개와 AI 활용 경험 나누기"
               for i in _unit(data, "w1")["items"])


def test_stub_change_request_validation_failure_is_422_not_500(client, example_id):
    """선수조건으로 쓰이는 활동 삭제 요청은 스텁 검증에서 걸려 422 쉬운 안내를 받는다."""
    response = client.post(
        f"/api/designs/{example_id}/change-requests",
        json={"text": "1주차 '1주차 확인 퀴즈'를 삭제"},
    )
    assert response.status_code == 422
    assert "문제가 생겨 보류" in response.json()["message"]
    path = design_path(example_id)
    # 파일은 그대로(검증만 하고 저장하지 않는다), 예시 원본도 그대로다
    assert hashlib.sha256(path.read_bytes()).hexdigest() == EXAMPLE_HASH


# --- 확정 해제 -------------------------------------------------------------------

def _confirm(client, design_id):
    response = client.post(f"/api/designs/{design_id}/confirm")
    assert response.status_code == 200, response.text


def test_successful_edit_unconfirms(client, example_id):
    _confirm(client, example_id)
    assert client.get(f"/api/designs/{example_id}").json()["confirmed"] is True

    edit = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [{"action": "update_unit", "unit_id": "w2", "summary": "고침"}]},
    )
    assert edit.status_code == 200
    assert edit.json()["confirmed"] is False
    assert client.get(f"/api/designs/{example_id}").json()["confirmed"] is False

    # 다시 확정할 수 있다
    _confirm(client, example_id)


def test_successful_change_request_apply_unconfirms(client, example_id):
    _confirm(client, example_id)
    preview = client.post(
        f"/api/designs/{example_id}/change-requests",
        json={"text": "2주차 제목을 '다시 바꾼 제목'로 바꿔 주세요"},
    ).json()
    applied = client.post(
        f"/api/designs/{example_id}/change-requests/{preview['request_id']}/apply"
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["confirmed"] is False


def test_failed_edit_keeps_confirmed_state(client, example_id):
    _confirm(client, example_id)
    failed = client.post(
        f"/api/designs/{example_id}/edits",
        json={"actions": [{"action": "remove_item", "unit_id": "w1", "item_id": "w1-quiz"}]},
    )
    assert failed.status_code == 409
    assert client.get(f"/api/designs/{example_id}").json()["confirmed"] is True


# --- 경로 조작 id 거부 --------------------------------------------------------------

@pytest.mark.parametrize("bad_id", ["../x", "..%2Fx", "a_b", "x y", "x.yaml", "."])
def test_path_manipulation_ids_are_rejected(client, bad_id):
    response = client.get(f"/api/designs/{bad_id}")
    assert response.status_code == 404


def test_path_manipulation_draft_ids_are_rejected(client):
    response = client.get("/api/drafts/..%2Fx")
    assert response.status_code == 404
    response = client.post("/api/drafts/a_b/design")
    assert response.status_code == 404


# --- 생성 결과 저장 전 검증 -----------------------------------------------------------

def test_injected_bad_design_payload_is_rejected_without_saving(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSESPEC_WEB_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.setenv("COURSESPEC_LLM_STUB", "1")
    client = TestClient(create_app(design_generate=lambda draft: {"broken": True}))

    created = client.post("/api/drafts", data={"title": "테스트 과정"})
    assert created.status_code == 200
    response = client.post(f"/api/drafts/{created.json()['id']}/design")
    assert response.status_code == 422
    assert "설계서" in response.json()["message"]
    assert not list((tmp_path / "workspace").rglob("*.coursespec.yaml"))


def test_injected_non_dict_design_payload_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("COURSESPEC_WEB_WORKSPACE", str(tmp_path / "workspace"))
    monkeypatch.setenv("COURSESPEC_LLM_STUB", "1")
    client = TestClient(create_app(design_generate=lambda draft: ["not", "a", "dict"]))

    created = client.post("/api/drafts", data={"title": "테스트 과정"})
    response = client.post(f"/api/drafts/{created.json()['id']}/design")
    assert response.status_code == 422
    assert not list((tmp_path / "workspace").rglob("*.coursespec.yaml"))
