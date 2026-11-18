"""과정 설계서(CourseSpec) 생성 — 설계 에이전트 역할.

인계 텍스트(M1 `handoff.draft_to_syllabus`)와 확정된 초안 필드를 받아
CourseSpec 0.2 설계서 dict 를 만든다. 이 모듈의 LLM 호출은 **설계서 생성과
"수정 요청" 문장 해석에만** 쓴다. `coursespec plan`/export 적용, LMS 실행,
설계서 확정, 배포에는 절대 쓰지 않는다.

키·주소는 **경로만** 다룬다. 파일 내용(값)은 로그·예외 메시지·응답·커밋에 넣지 않는다.
테스트·로컬 데모는 `COURSESPEC_LLM_STUB=1`(또는 호출 객체 주입)로 네트워크 없이 돌린다.
"""

from __future__ import annotations

import copy
import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Callable

from ..patch import PatchError, patch_file
from .errors import DraftError, WebError
from .handoff import draft_to_syllabus

ENV_STUB = "COURSESPEC_LLM_STUB"
ENV_KEY_PATH = "COURSESPEC_LLM_KEY_PATH"
ENV_URL_PATH = "COURSESPEC_LLM_URL_PATH"
ENV_MODEL = "COURSESPEC_LLM_MODEL"

MODEL_MISSING_MESSAGE = (
    "모델 연결 정보가 없습니다. 경로를 설정하거나 잠시 후 다시 시도해 주세요."
)

_SYSTEM_PROMPT = (
    "당신은 대학 교수를 돕는 과정 설계 에이전트입니다. 강의계획서 텍스트를 받아 "
    "CourseSpec 0.2 형식의 과정 설계서 JSON 을 만듭니다. "
    "이 출력은 교수가 검토하는 설계서 초안이며, LMS 실행이나 배포에는 쓰이지 않습니다. "
    "반드시 아래 JSON 형식만 출력하고 다른 설명은 붙이지 마세요."
)

_DEFAULT_GRADING = [
    {"name": "퀴즈", "weight": 20},
    {"name": "토론", "weight": 20},
    {"name": "설계 과제", "weight": 60},
]

_LEVELS = ["understand", "apply", "analyze", "evaluate", "create"]

# 화면에서 쓰는 한국어 활동 유형 ↔ 스펙 type
# '자료' 는 뺀다: 파일 업로드 없이 가짜 경로를 넣을 수밖에 없어서, 추가 자체를 지원하지 않는다.
KIND_TO_TYPE = {
    "읽기": "page",
    "퀴즈": "quiz",
    "토론": "discussion",
    "과제": "assignment",
    "동료평가": "peer_review",
    "설문": "survey",
    "위키": "wiki",
    "수업": "interactive_lecture",
}


def build_design_messages(handoff_text: str, draft: dict) -> list[dict]:
    """설계서 생성용 대화 메시지를 만든다."""
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "아래 강의계획서를 CourseSpec 0.2 설계서 JSON 으로 바꿔 주세요.\n"
                "- coursespec: \"0.2\", id, title, language(ko), summary\n"
                "- outcomes: [{id: lo1.., statement, level(remember|understand|apply|"
                "analyze|evaluate|create)}]\n"
                "- grading: {aggregation: weighted_mean, categories: [{id, name, weight}]}\n"
                "- policies: {workload: {max_minutes_per_unit: 240}}\n"
                "- units: [{id: w1.., title, summary, opens_day, items: [...]}]\n"
                "  활동(item)은 id, type(page|file|quiz|discussion|assignment|peer_review|"
                "survey...), title, outcomes, estimated_minutes, completion, "
                "그리고 평가 활동은 grading{max, category}와 상대 일수(opens_day/due_day)를 갖습니다.\n"
                "강의계획서:\n"
                + handoff_text
            ),
        },
    ]


# --- 결정적 스텁 --------------------------------------------------------------

def _category_type(name: str) -> str:
    if "퀴즈" in name:
        return "quiz"
    if "토론" in name or "참여" in name:
        return "discussion"
    if "동료" in name:
        return "peer_review"
    return "assignment"


def _graded_item(unit_no: int, opens_day: int, item_type: str, category_id: str,
                 lo_id: str, week_title: str) -> dict:
    """평가 활동 하나를 만든다. 린트 경고가 나오지 않도록 완결하게 구성한다."""
    if item_type == "quiz":
        return {
            "id": f"w{unit_no}-quiz",
            "type": "quiz",
            "title": f"{unit_no}주차 확인 퀴즈",
            "outcomes": [lo_id],
            "estimated_minutes": 15,
            "due_day": opens_day + 6,
            "grading": {"max": 10, "category": category_id},
            "quiz": {"time_limit_minutes": 15, "attempts": 2, "grade_method": "highest"},
            "completion": {"mode": "pass", "pass_grade": 6},
            "questions": [
                {
                    "type": "multichoice",
                    "text": f"{week_title}의 핵심 개념을 확인하는 문항입니다.",
                    "choices": [
                        {"text": "보기 1"},
                        {"text": "보기 2", "correct": True,
                         "feedback": "맞습니다. 핵심 개념을 잘 이해했습니다."},
                    ],
                },
                {"type": "truefalse", "text": "이 주차의 개념은 암기보다 적용이 중요합니다.",
                 "answer": True},
            ],
        }
    if item_type == "discussion":
        return {
            "id": f"w{unit_no}-forum",
            "type": "discussion",
            "title": f"{unit_no}주차 토론 — {week_title}",
            "outcomes": [lo_id],
            "estimated_minutes": 20,
            "discussion": {"style": "general"},
            "grading": {"max": 10, "category": category_id},
            "completion": {"mode": "posts", "posts": 2},
        }
    if item_type == "peer_review":
        return {
            "id": f"w{unit_no}-peer",
            "type": "peer_review",
            "title": f"{unit_no}주차 동료 평가 — {week_title}",
            "outcomes": [lo_id],
            "estimated_minutes": 30,
            "due_day": opens_day + 6,
            "grading": {"max": 20, "category": category_id},
            "submission": {"types": ["text"]},
            "peer_review": {"assessment_max": 10, "assessment_due_day": opens_day + 8},
            "completion": {"mode": "submit"},
        }
    return {
        "id": f"w{unit_no}-assignment",
        "type": "assignment",
        "title": f"과제 — {week_title} 적용하기",
        "outcomes": [lo_id],
        "estimated_minutes": 60,
        "due_day": opens_day + 6,
        "cutoff_day": opens_day + 9,
        "grading": {"max": 100, "category": category_id},
        "submission": {"types": ["text", "file"], "max_files": 2},
        "completion": {"mode": "submit"},
    }


def stub_design(handoff_text: str, draft: dict) -> dict:
    """네트워크 없이 초안 필드를 그대로 반영한 결정적 설계서를 만든다.

    교수가 고친 과정 이름, 주차 제목·요약, 학습목표, 평가 비중이 설계서에
    그대로 들어간다. 결과는 스키마 오류 0, 린트 오류 0 이다.
    """
    title = (draft.get("title") or "").strip() or "이름 없는 과정"
    weeks = draft.get("weeks") or []
    if not weeks:
        weeks = [{"title": "전체 학습 활동", "summary": "과정의 핵심 내용을 함께 다룹니다."}]
    outcomes = [str(o).strip() for o in (draft.get("outcomes") or []) if str(o).strip()]

    grading = [
        {"name": str(g.get("name") or "").strip(), "weight": int(g.get("weight") or 0)}
        for g in (draft.get("grading") or [])
        if str(g.get("name") or "").strip()
    ] or [dict(g) for g in _DEFAULT_GRADING]
    categories = [
        {"id": f"g{i + 1}", "name": g["name"], "weight": g["weight"]}
        for i, g in enumerate(grading)
    ]

    lo_ids = [f"lo{i + 1}" for i in range(len(outcomes))]

    # 평가 항목마다 활동 유형을 정해 주차에 배치한다 (퀴즈는 1주차, 나머지는 2주차부터).
    plan: list[tuple[int, str, str]] = []  # (주차 번호, 카테고리 id, 활동 유형)
    extra_slot = 1
    for cat in categories:
        item_type = _category_type(cat["name"])
        if item_type == "quiz":
            week_no = 1
        else:
            week_no = min(extra_slot + 1, len(weeks))
            extra_slot += 1
        plan.append((week_no, cat["id"], item_type))

    units: list[dict[str, Any]] = []
    for i, week in enumerate(weeks, 1):
        week_title = (week.get("title") or "").strip() or f"{i}주차 학습"
        week_summary = (week.get("summary") or "").strip()
        opens_day = (i - 1) * 7 + 1
        lo_id = lo_ids[(i - 1) % len(lo_ids)] if lo_ids else None

        items: list[dict[str, Any]] = [
            {
                "id": f"w{i}-reading",
                "type": "page",
                "title": f"읽기 — {week_title}",
                "outcomes": [lo_id] if lo_id else [],
                "estimated_minutes": 30,
                "content": (week_summary or f"{week_title}의 핵심 개념을 정리합니다.")
                + " 이 자료를 읽고 핵심 개념을 정리합니다.",
                "completion": {"mode": "view"},
            }
        ]
        for week_no, cat_id, item_type in plan:
            if week_no == i and lo_id:
                items.append(_graded_item(i, opens_day, item_type, cat_id, lo_id, week_title))

        units.append(
            {
                "id": f"w{i}",
                "title": f"{i}주차 — {week_title}",
                "summary": week_summary,
                "opens_day": opens_day,
                "items": items,
            }
        )

    return {
        "coursespec": "0.2",
        "id": "draft-design",
        "title": title,
        "language": "ko",
        "timezone": "Asia/Seoul",
        "summary": (draft.get("intro") or "").strip() or f"{title}의 핵심을 다루는 과정입니다.",
        "outcomes": [
            {"id": lo_ids[i], "statement": statement, "level": _LEVELS[i % len(_LEVELS)]}
            for i, statement in enumerate(outcomes)
        ],
        "grading": {"aggregation": "weighted_mean", "categories": categories},
        "policies": {"workload": {"max_minutes_per_unit": 240}},
        "units": units,
    }


# --- 수정 요청 해석 (결정적 스텁) ----------------------------------------------

_CHANGE_TITLE = re.compile(
    r"(\d{1,2})\s*주차\s*제목을\s*['\"‘“]?(.+?)['\"’”]?\s*로\s*바꿔"
)
_CHANGE_ADD = re.compile(
    r"(\d{1,2})\s*주차에\s*(읽기|퀴즈|토론|과제|설문|동료평가|수업)\s*"
    r"(?:['\"‘“](.+?)['\"’”])?\s*추가"
)
_CHANGE_REMOVE = re.compile(
    r"(\d{1,2})\s*주차\s*['\"‘“](.+?)['\"’”]\s*(?:을|를)\s*삭제"
)
_CHANGE_DUE = re.compile(
    r"(\d{1,2})\s*주차\s*['\"‘“](.+?)['\"’”]\s*마감(?:일)?을?\s*(\d{1,3})\s*일(?:차)?로?"
)
_CHANGE_MINUTES = re.compile(
    r"(\d{1,2})\s*주차\s*['\"‘“](.+?)['\"’”]\s*(\d{1,4})\s*분으로?"
)


def _unit_at(data: dict, week_no: int) -> tuple[int, dict]:
    units = data.get("units") or []
    if not 1 <= week_no <= len(units):
        raise WebError(f"{week_no}주차를 찾지 못했습니다. 설계서의 주차 수를 확인해 주세요.", status=404)
    return week_no - 1, units[week_no - 1]


def _find_item(unit: dict, title: str) -> tuple[int, dict]:
    for j, item in enumerate(unit.get("items") or []):
        if item.get("title") == title:
            return j, item
    raise WebError(
        f"'{unit.get('title', '')}'에서 '{title}' 활동을 찾지 못했습니다. 활동 이름을 그대로 적어 주세요.",
        status=404,
    )


def _new_item_id(unit: dict, item_type: str) -> str:
    base = f"{unit['id']}-{item_type.replace('_', '')}"
    existing = {it.get("id") for it in unit.get("items") or []}
    if base not in existing:
        return base
    n = 2
    while f"{base}{n}" in existing:
        n += 1
    return f"{base}{n}"


def _minimal_item(unit: dict, kind: str, title: str, minutes: int) -> dict:
    item_type = KIND_TO_TYPE.get(kind, "page")
    item: dict[str, Any] = {
        "id": _new_item_id(unit, item_type),
        "type": item_type,
        "title": title.strip() or f"새 {kind}",
        "estimated_minutes": minutes,
    }
    if item_type == "page":
        item["content"] = f"{item['title']}의 내용을 정리해 주세요."
        item["completion"] = {"mode": "view"}
    elif item_type == "quiz":
        item["quiz"] = {"time_limit_minutes": minutes, "attempts": 1}
        item["completion"] = {"mode": "pass", "pass_grade": 1}
        item["questions"] = [
            {
                "type": "multichoice",
                "text": f"{item['title']}의 핵심을 확인하는 문항입니다.",
                "choices": [{"text": "보기 1"}, {"text": "보기 2", "correct": True}],
            }
        ]
    elif item_type == "discussion":
        item["discussion"] = {"style": "general"}
        item["completion"] = {"mode": "posts", "posts": 1}
    elif item_type in ("assignment", "peer_review", "survey"):
        item["submission"] = {"types": ["text"]}
        item["completion"] = {"mode": "submit"}
    elif item_type == "interactive_lecture":
        item["lecture"] = {"engine": "openmaic", "prompt": item["title"]}
        item["completion"] = {"mode": "view"}
    return item


def _dry_run_checked(path: Any, ops: list[dict]) -> None:
    """스텁이 만든 연산도 검증한다. 실패하면 쉬운 한국어 422 로 안내한다(500 이 아니다)."""
    try:
        patch_file(path, ops, dry_run=True)
    except PatchError:
        raise WebError(
            "요청하신 변경을 적용하면 설계서에 문제가 생겨 보류했습니다. "
            "다른 표현으로 다시 요청해 주세요.",
            status=422,
        ) from None


def stub_change_request(text: str, data: dict, path: Any) -> tuple[list[dict], list[str]]:
    """"수정 요청" 문장을 검증된 JSON Patch 와 쉬운 한국어 변경 요약으로 바꾼다.

    알아듣지 못한 문장은 None 이 아니라 WebError(400) 로 안내한다.
    삭제·추가 연산에도 대상 id 를 확인하는 test 를 함께 둔다.
    """
    match = _CHANGE_TITLE.search(text)
    if match:
        week_no, new_title = int(match.group(1)), match.group(2).strip()
        ui, unit = _unit_at(data, week_no)
        old_title = unit.get("title", "")
        ops = [
            {"op": "test", "path": f"/units/{ui}/id", "value": unit.get("id")},
            {"op": "test", "path": f"/units/{ui}/title", "value": old_title},
            {"op": "replace", "path": f"/units/{ui}/title", "value": new_title},
        ]
        _dry_run_checked(path, ops)
        return ops, [f"{week_no}주차 제목을 '{new_title}'(으)로 바꿉니다."]

    match = _CHANGE_ADD.search(text)
    if match:
        week_no, kind, title = int(match.group(1)), match.group(2), match.group(3) or ""
        ui, unit = _unit_at(data, week_no)
        item = _minimal_item(unit, kind, title, 30)
        ops = [
            {"op": "test", "path": f"/units/{ui}/id", "value": unit.get("id")},
            {"op": "add", "path": f"/units/{ui}/items/-", "value": item},
        ]
        _dry_run_checked(path, ops)
        return ops, [f"{week_no}주차에 {kind} '{item['title']}'을(를) 추가합니다."]

    match = _CHANGE_REMOVE.search(text)
    if match:
        week_no, title = int(match.group(1)), match.group(2).strip()
        ui, unit = _unit_at(data, week_no)
        ji, item = _find_item(unit, title)
        ops = [
            {"op": "test", "path": f"/units/{ui}/items/{ji}/id", "value": item.get("id")},
            {"op": "remove", "path": f"/units/{ui}/items/{ji}"},
        ]
        _dry_run_checked(path, ops)
        return ops, [f"{week_no}주차의 '{title}' 활동을 뺍니다."]

    match = _CHANGE_DUE.search(text)
    if match:
        week_no, title, due = int(match.group(1)), match.group(2).strip(), int(match.group(3))
        ui, unit = _unit_at(data, week_no)
        ji, item = _find_item(unit, title)
        ops = [
            {"op": "test", "path": f"/units/{ui}/items/{ji}/id", "value": item.get("id")},
            {"op": "replace", "path": f"/units/{ui}/items/{ji}/due_day", "value": due},
        ]
        _dry_run_checked(path, ops)
        return ops, [f"{week_no}주차 '{title}'의 마감을 {due}일차로 바꿉니다."]

    match = _CHANGE_MINUTES.search(text)
    if match:
        week_no, title, minutes = int(match.group(1)), match.group(2).strip(), int(match.group(3))
        ui, unit = _unit_at(data, week_no)
        ji, item = _find_item(unit, title)
        ops = [
            {"op": "test", "path": f"/units/{ui}/items/{ji}/id", "value": item.get("id")},
            {"op": "replace", "path": f"/units/{ui}/items/{ji}/estimated_minutes", "value": minutes},
        ]
        _dry_run_checked(path, ops)
        return ops, [f"{week_no}주차 '{title}'의 소요 시간을 {minutes}분으로 바꿉니다."]

    raise WebError(
        "아직 이해하지 못했어요. 예를 들어 '3주차에 토론 추가' 또는 "
        "'2주차 제목을 …로 바꿔 주세요'처럼 주차와 바꿀 내용을 함께 말씀해 주세요.",
        status=400,
    )


# --- 실제 LLM 호출 (테스트·로컬 데모에서는 쓰지 않는다) -------------------------

def _read_secret_path(env_name: str) -> str | None:
    path = os.environ.get(env_name)
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return None


def _parse_json_content(content: str, what: str) -> dict:
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise DraftError(f"{what} 만들지 못했습니다. 모델 응답이 JSON 이 아닙니다.")
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise DraftError(f"{what} 만들지 못했습니다. 모델 응답을 읽지 못했습니다.") from exc
    if not isinstance(payload, dict):
        raise DraftError(f"{what} 만들지 못했습니다. 모델 응답 형식이 올바르지 않습니다.")
    return payload


def _call_llm(messages: list[dict], what: str) -> dict:
    """키·주소 경로를 읽어 OpenAI 호환 채팅 API 를 호출한다. 값은 절대 로그에 남기지 않는다."""
    key = _read_secret_path(ENV_KEY_PATH)
    url = _read_secret_path(ENV_URL_PATH)
    if not key or not url:
        raise DraftError(MODEL_MISSING_MESSAGE)
    if not url.lower().startswith("https://"):
        raise DraftError("모델 주소가 올바르지 않습니다. 주소를 확인하고 다시 시도해 주세요.")

    body: dict = {"messages": messages, "temperature": 0.4}
    model = os.environ.get(ENV_MODEL) or None
    if model:
        body["model"] = model

    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise DraftError(f"{what} 만들지 못했습니다. 잠시 후 다시 시도해 주세요.") from exc
    except urllib.error.URLError as exc:
        raise DraftError(f"{what} 만들지 못했습니다. 연결을 확인하고 다시 시도해 주세요.") from exc

    try:
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise DraftError(f"{what} 만들지 못했습니다. 모델 응답을 읽지 못했습니다.") from exc
    return _parse_json_content(content, what)


def _validate_design_payload(payload: dict) -> dict:
    """실모델이 만든 설계서를 스키마·린트로 검증한다. 문제가 있으면 저장하지 않는다."""
    from ..lint import lint
    from ..spec import SpecError, from_data

    try:
        spec = from_data(payload)
    except SpecError:
        raise DraftError(
            "만들어진 설계서에 형식 문제가 있어 저장하지 않았습니다. 다시 시도해 주세요."
        ) from None
    errors = [f for f in lint(spec) if f.is_error]
    if errors:
        raise DraftError(
            "만들어진 설계서에 설계 오류가 있어 저장하지 않았습니다. 다시 시도해 주세요."
        )
    return copy.deepcopy(payload)


def validate_design_payload(payload: Any) -> dict:
    """스텁·주입·실모델 결과를 가리지 않고 저장 전 스키마·린트 검증을 한다.

    문제가 있으면 WebError(422) — 설계서 파일은 저장되지 않는다.
    """
    try:
        return _validate_design_payload(payload)
    except DraftError as exc:
        raise WebError(exc.message, status=422) from None


# --- 진입점 -------------------------------------------------------------------

def generate_design(
    draft: dict,
    call: Callable[[str, dict], dict] | None = None,
) -> dict:
    """설계서 dict(CourseSpec 0.2)를 만든다.

    - `call` 이 주어지면 `call(handoff_text, draft)` 로 결과 dict 를 받는다 (테스트 주입).
    - `COURSESPEC_LLM_STUB=1` 이면 결정적 스텁을 쓴다 (테스트·로컬 데모).
    - 둘 다 아니면 키·주소 경로를 읽어 실제 호출을 시도한다.
    """
    handoff_text = draft_to_syllabus(draft)
    if call is not None:
        return call(handoff_text, draft)
    if os.environ.get(ENV_STUB) == "1":
        return stub_design(handoff_text, draft)
    payload = _call_llm(build_design_messages(handoff_text, draft), "설계서를")
    return _validate_design_payload(payload)


_CHANGE_SYSTEM_PROMPT = (
    "당신은 대학 교수의 '수정 요청' 문장을 JSON Patch(RFC 6902, add·replace·remove·test)와 "
    "쉬운 한국어 변경 요약으로 바꾸는 도우미입니다. "
    "반드시 아래 JSON 형식만 출력하세요: "
    '{"ops": [{"op": "...", "path": "/units/...", "value": ...}], "summary": ["한국어 변경 문장"]}'
)


def interpret_change_request(
    text: str,
    data: dict,
    path: Any,
    call: Callable[[str, dict], dict] | None = None,
) -> tuple[list[dict], list[str]]:
    """자유 문장 수정 요청을 검증된 JSON Patch 와 변경 요약으로 바꾼다.

    스텁(`COURSESPEC_LLM_STUB=1`)이면 결정적 패턴 해석을, 아니면 실모델 호출을 쓴다.
    어떤 경로든 검증(dry-run)을 통과하지 못하면 저장하지 않고 한국어로 안내한다.
    """
    if call is not None:
        payload = call(text, data)
        ops, summary = _coerce_change_payload(payload)
    elif os.environ.get(ENV_STUB) == "1":
        return stub_change_request(text, data, path)
    else:
        messages = [
            {"role": "system", "content": _CHANGE_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False) + "\n\n수정 요청: " + text},
        ]
        payload = _call_llm(messages, "변경 내용을")
        ops, summary = _coerce_change_payload(payload)

    _check_ops(ops)
    try:
        patch_file(path, ops, dry_run=True)
    except PatchError:
        raise WebError(
            "요청하신 변경을 적용하면 설계서에 문제가 생겨 보류했습니다. "
            "다른 표현으로 다시 요청해 주세요.",
            status=422,
        ) from None
    return ops, summary


def _coerce_change_payload(payload: Any) -> tuple[list[dict], list[str]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("ops"), list):
        raise WebError("수정 요청을 이해하지 못했습니다. 다시 말씀해 주세요.", status=400)
    summary = payload.get("summary")
    if not isinstance(summary, list) or not all(isinstance(s, str) for s in summary):
        summary = []
    return payload["ops"], [str(s) for s in summary]


def _check_ops(ops: list[Any]) -> None:
    if not ops:
        raise WebError("수정 요청을 이해하지 못했습니다. 다시 말씀해 주세요.", status=400)
    for op in ops:
        if not isinstance(op, dict) or op.get("op") not in ("add", "replace", "remove", "test"):
            raise WebError("수정 요청을 이해하지 못했습니다. 다시 말씀해 주세요.", status=400)
        if not isinstance(op.get("path"), str) or not op["path"].startswith("/"):
            raise WebError("수정 요청을 이해하지 못했습니다. 다시 말씀해 주세요.", status=400)
