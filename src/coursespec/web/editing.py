"""화면 편집 요청(구조화된 동작)을 검증된 JSON Patch 로 변환한다.

교수 화면의 "주차 제목 고치기, 활동 시간·마감 고치기, 활동 추가·삭제·이동"은
여기서 `test`+`replace`/`add`/`remove` 연산으로 바뀌고, `coursespec.patch.patch_file` 로
검증돼야만 파일에 기록된다. 검증 실패 시 파일은 그대로다. 교수는 패치를 보지 않는다.

한 번에 여러 동작이 오면 각 동작은 **직전 동작까지 적용된 문서**를 기준으로 연산을 만든다.
그래서 앞 활동을 빼거나 옮긴 뒤 뒤 활동을 고쳐도 순번이 어긋나지 않는다. 대상 확인용
`test`는 바뀔 수 있는 값(제목)이 아니라 활동 `id` 를 본다.
"""

from __future__ import annotations

import copy
from typing import Any

from ..patch import PatchError, apply_ops, patch_file
from .design import KIND_TO_TYPE, _minimal_item  # 화면 유형 ↔ 스펙 유형 공용 매핑
from .errors import WebError


def _unit_index(data: dict, unit_id: str) -> tuple[int, dict]:
    for i, unit in enumerate(data.get("units") or []):
        if unit.get("id") == unit_id:
            return i, unit
    raise WebError("해당 주차를 찾지 못했습니다. 화면을 새로 고친 뒤 다시 시도해 주세요.", status=404)


def _item_index(unit: dict, item_id: str) -> tuple[int, dict]:
    for j, item in enumerate(unit.get("items") or []):
        if item.get("id") == item_id:
            return j, item
    raise WebError("해당 활동을 찾지 못했습니다. 화면을 새로 고친 뒤 다시 시도해 주세요.", status=404)


def _id_test(base: str, current_id: Any) -> dict[str, Any]:
    """대상이 바뀐 문서에서도 같은 항목인지 확인하는 test 연산(활동/주차 id 기준)."""
    return {"op": "test", "path": f"{base}/id", "value": current_id}


def _update_unit_ops(data: dict, action: dict[str, Any]) -> list[dict[str, Any]]:
    ui, unit = _unit_index(data, str(action.get("unit_id") or ""))
    base = f"/units/{ui}"
    ops: list[dict[str, Any]] = []
    changed = False
    if "title" in action and action["title"] is not None:
        title = str(action["title"]).strip()
        if not title:
            raise WebError("주차 제목을 비워 둘 수 없습니다.", status=422)
        if title != (unit.get("title") or ""):
            ops.append(_id_test(base, unit.get("id")))
            ops.append({"op": "replace", "path": f"{base}/title", "value": title})
            changed = True
    if "summary" in action and action["summary"] is not None:
        summary = str(action["summary"])
        if summary != (unit.get("summary") or ""):
            if not changed:
                ops.append(_id_test(base, unit.get("id")))
            # 키가 없는 주차에는 새로 넣고, 있으면 고친다.
            ops.append(
                {"op": "replace", "path": f"{base}/summary", "value": summary}
                if "summary" in unit
                else {"op": "add", "path": f"{base}/summary", "value": summary}
            )
    return ops


def _update_item_ops(data: dict, action: dict[str, Any]) -> list[dict[str, Any]]:
    ui, unit = _unit_index(data, str(action.get("unit_id") or ""))
    ji, item = _item_index(unit, str(action.get("item_id") or ""))
    base = f"/units/{ui}/items/{ji}"
    ops: list[dict[str, Any]] = []
    changed = False

    def _guard() -> None:
        nonlocal changed
        if not changed:
            ops.append(_id_test(base, item.get("id")))
            changed = True

    if "title" in action and action["title"] is not None:
        title = str(action["title"]).strip()
        if not title:
            raise WebError("활동 제목을 비워 둘 수 없습니다.", status=422)
        if title != (item.get("title") or ""):
            _guard()
            ops.append({"op": "replace", "path": f"{base}/title", "value": title})
    if "minutes" in action and action["minutes"] is not None:
        minutes = int(action["minutes"])
        if minutes < 0:
            raise WebError("소요 시간은 0분 이상이어야 합니다.", status=422)
        if minutes != item.get("estimated_minutes"):
            _guard()
            ops.append({"op": "replace", "path": f"{base}/estimated_minutes", "value": minutes})
    if "due_day" in action:  # 명시적으로 준 경우에만(없음(null)은 마감 삭제)
        due = action["due_day"]
        if due is not None:
            due = int(due)
            if due < 1:
                raise WebError("마감일은 1일차 이후여야 합니다.", status=422)
            if due != item.get("due_day"):
                _guard()
                # 키가 있으면 고치고, 없으면 새로 넣는다.
                ops.append(
                    {"op": "replace", "path": f"{base}/due_day", "value": due}
                    if "due_day" in item
                    else {"op": "add", "path": f"{base}/due_day", "value": due}
                )
        elif "due_day" in item:
            _guard()
            ops.append({"op": "remove", "path": f"{base}/due_day"})
    return ops


def _add_item_ops(data: dict, action: dict[str, Any]) -> list[dict[str, Any]]:
    ui, unit = _unit_index(data, str(action.get("unit_id") or ""))
    label = str(action.get("kind") or "")
    if label not in KIND_TO_TYPE:
        raise WebError("추가할 활동 유형을 선택해 주세요.", status=422)
    title = str(action.get("title") or "").strip() or f"새 {label}"
    minutes = int(action.get("minutes") or 30)
    if minutes < 0:
        raise WebError("소요 시간은 0분 이상이어야 합니다.", status=422)
    # 설계서 전체 이름공간 기준으로 id 를 정해, 다른 주차로 옮긴 활동과도 겹치지 않는다.
    item = _minimal_item(data, unit, label, title, minutes)
    return [
        _id_test(f"/units/{ui}", unit.get("id")),
        {"op": "add", "path": f"/units/{ui}/items/-", "value": item},
    ]


def _remove_item_ops(data: dict, action: dict[str, Any]) -> list[dict[str, Any]]:
    ui, unit = _unit_index(data, str(action.get("unit_id") or ""))
    ji, item = _item_index(unit, str(action.get("item_id") or ""))
    base = f"/units/{ui}/items/{ji}"
    return [_id_test(base, item.get("id")), {"op": "remove", "path": base}]


def _move_item_ops(data: dict, action: dict[str, Any]) -> list[dict[str, Any]]:
    si, s_unit = _unit_index(data, str(action.get("unit_id") or ""))
    ji, item = _item_index(s_unit, str(action.get("item_id") or ""))
    ti, _ = _unit_index(data, str(action.get("to_unit_id") or ""))
    if si == ti:
        raise WebError("활동이 이미 그 주차에 있습니다. 다른 주차를 선택해 주세요.", status=422)
    base = f"/units/{si}/items/{ji}"
    return [
        _id_test(base, item.get("id")),
        {"op": "remove", "path": base},
        {"op": "add", "path": f"/units/{ti}/items/-", "value": copy.deepcopy(item)},
    ]


def build_edit_ops(data: dict, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """구조화된 편집 동작 목록을 검증용 JSON Patch 연산 목록으로 바꾼다.

    동작마다 직전까지의 적용 결과 문서를 기준으로 연산을 만들어, 한 번에 여러 동작을
    묶어 본낼 때도 순번이 어긋나지 않는다.
    """
    builders = {
        "update_unit": _update_unit_ops,
        "update_item": _update_item_ops,
        "add_item": _add_item_ops,
        "remove_item": _remove_item_ops,
        "move_item": _move_item_ops,
    }
    ops: list[dict[str, Any]] = []
    work = copy.deepcopy(data)
    for action in actions:
        builder = builders.get(str(action.get("action") or ""))
        if builder is None:
            raise WebError("알 수 없는 편집 동작입니다. 화면을 새로 고친 뒤 다시 시도해 주세요.", status=400)
        step_ops = builder(work, action)
        if step_ops:
            work = apply_ops(work, step_ops)
            ops.extend(step_ops)
    return ops


def apply_edits(path: Any, data: dict, actions: list[dict[str, Any]]) -> list:
    """편집을 검증 적용한다. 스키마·린트 오류가 생기면 파일은 그대로 두고 WebError 를 던진다."""
    if not actions:
        raise WebError("바꿀 내용이 없습니다.", status=422)
    ops = build_edit_ops(data, actions)
    if not ops:
        raise WebError("바뀐 내용이 없습니다. 바꿀 값을 조금이라도 고쳐 주세요.", status=422)
    try:
        return patch_file(path, ops)
    except PatchError as exc:
        # 남은 id 충돌(E001)은 교수가 고칠 수 있는 제목 문제가 아니므로
        # "다시 시도해 주세요" 안내로 돌린다.
        if exc.errors:
            raise WebError(
                "고친 내용을 적용하면 설계서에 문제가 생깁니다. "
                "선수조건으로 쓰이는 활동을 빼거나 다른 주차로 옮긴 것은 아닌지 확인해 주세요.",
                status=409,
            ) from None
        raise WebError(
            "고친 내용을 적용하지 못했습니다. 화면을 새로 고친 뒤 다시 시도해 주세요.",
            status=409,
        ) from None
