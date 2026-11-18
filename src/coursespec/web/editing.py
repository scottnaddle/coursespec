"""화면 편집 요청(구조화된 동작)을 검증된 JSON Patch 로 변환한다.

교수 화면의 "주차 제목 고치기, 활동 시간·마감 고치기, 활동 추가·삭제·이동"은
여기서 `test`+`replace`/`add`/`remove` 연산으로 바뀌고, `coursespec.patch.patch_file` 로
검증돼야만 파일에 기록된다. 검증 실패 시 파일은 그대로다. 교수는 패치를 보지 않는다.
"""

from __future__ import annotations

import copy
from typing import Any

from ..patch import PatchError, patch_file
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


def build_edit_ops(data: dict, actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """구조화된 편집 동작 목록을 검증용 JSON Patch 연산 목록으로 바꾼다."""
    ops: list[dict[str, Any]] = []
    for action in actions:
        kind = action.get("action")
        if kind == "update_unit":
            ui, unit = _unit_index(data, str(action.get("unit_id") or ""))
            if "title" in action and action["title"] is not None:
                title = str(action["title"]).strip()
                if not title:
                    raise WebError("주차 제목을 비워 둘 수 없습니다.", status=422)
                ops.append({"op": "test", "path": f"/units/{ui}/title", "value": unit.get("title")})
                ops.append({"op": "replace", "path": f"/units/{ui}/title", "value": title})
            if "summary" in action and action["summary"] is not None:
                summary = str(action["summary"])
                ops.append({"op": "test", "path": f"/units/{ui}/summary", "value": unit.get("summary", "")})
                ops.append({"op": "replace", "path": f"/units/{ui}/summary", "value": summary})
        elif kind == "update_item":
            ui, unit = _unit_index(data, str(action.get("unit_id") or ""))
            ji, item = _item_index(unit, str(action.get("item_id") or ""))
            base = f"/units/{ui}/items/{ji}"
            if "title" in action and action["title"] is not None:
                title = str(action["title"]).strip()
                if not title:
                    raise WebError("활동 제목을 비워 둘 수 없습니다.", status=422)
                ops.append({"op": "test", "path": f"{base}/title", "value": item.get("title")})
                ops.append({"op": "replace", "path": f"{base}/title", "value": title})
            if "minutes" in action and action["minutes"] is not None:
                minutes = int(action["minutes"])
                if minutes < 0:
                    raise WebError("소요 시간은 0분 이상이어야 합니다.", status=422)
                ops.append({"op": "test", "path": f"{base}/estimated_minutes", "value": item.get("estimated_minutes")})
                ops.append({"op": "replace", "path": f"{base}/estimated_minutes", "value": minutes})
            if "due_day" in action:  # 명시적으로 준 경우에만(없음(null)은 마감 삭제)
                due = action["due_day"]
                if due is not None:
                    due = int(due)
                    if due < 1:
                        raise WebError("마감일은 1일차 이후여야 합니다.", status=422)
                    if "due_day" in item:
                        ops.append({"op": "test", "path": f"{base}/title", "value": item.get("title")})
                        ops.append({"op": "replace", "path": f"{base}/due_day", "value": due})
                    else:
                        ops.append({"op": "add", "path": f"{base}/due_day", "value": due})
                elif "due_day" in item:
                    ops.append({"op": "test", "path": f"{base}/title", "value": item.get("title")})
                    ops.append({"op": "remove", "path": f"{base}/due_day"})
        elif kind == "add_item":
            ui, unit = _unit_index(data, str(action.get("unit_id") or ""))
            label = str(action.get("kind") or "")
            if label not in KIND_TO_TYPE:
                raise WebError("추가할 활동 유형을 선택해 주세요.", status=422)
            title = str(action.get("title") or "").strip() or f"새 {label}"
            minutes = int(action.get("minutes") or 30)
            if minutes < 0:
                raise WebError("소요 시간은 0분 이상이어야 합니다.", status=422)
            item = _minimal_item(unit, label, title, minutes)
            ops.append({"op": "add", "path": f"/units/{ui}/items/-", "value": item})
        elif kind == "remove_item":
            ui, unit = _unit_index(data, str(action.get("unit_id") or ""))
            ji, item = _item_index(unit, str(action.get("item_id") or ""))
            ops.append({"op": "test", "path": f"/units/{ui}/items/{ji}/id", "value": item.get("id")})
            ops.append({"op": "remove", "path": f"/units/{ui}/items/{ji}"})
        elif kind == "move_item":
            si, s_unit = _unit_index(data, str(action.get("unit_id") or ""))
            ji, item = _item_index(s_unit, str(action.get("item_id") or ""))
            ti, _ = _unit_index(data, str(action.get("to_unit_id") or ""))
            if si == ti:
                raise WebError("활동이 이미 그 주차에 있습니다. 다른 주차를 선택해 주세요.", status=422)
            ops.append({"op": "test", "path": f"/units/{si}/items/{ji}/id", "value": item.get("id")})
            ops.append({"op": "remove", "path": f"/units/{si}/items/{ji}"})
            ops.append({"op": "add", "path": f"/units/{ti}/items/-", "value": copy.deepcopy(item)})
        else:
            raise WebError("알 수 없는 편집 동작입니다. 화면을 새로 고친 뒤 다시 시도해 주세요.", status=400)
    return ops


def apply_edits(path: Any, data: dict, actions: list[dict[str, Any]]) -> list:
    """편집을 검증 적용한다. 스키마·린트 오류가 생기면 파일은 그대로 두고 WebError 를 던진다."""
    if not actions:
        raise WebError("바꿀 내용이 없습니다.", status=422)
    ops = build_edit_ops(data, actions)
    try:
        return patch_file(path, ops)
    except PatchError as exc:
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
