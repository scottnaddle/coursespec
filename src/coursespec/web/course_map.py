"""설계서 → 화면 모델(JSON). 교수 화면에 YAML·JSON Patch·린트 코드·도구 이름이
보이지 않게, 쉬운 한국어로만 구성한다.

- 상단 요약 칩: 주차 수, 학습목표 수, 평가 비중(“과제 60% · 퀴즈 20% · …”), 주당 최대 학습시간
- 학습목표 카드: “목표 1 · 이해” 같은 한국어 수준 라벨
- 주차 카드: 제목·요약·총 분, 활동 행(유형 한국어 배지, 분, “N일차 마감”)
- 린트 결과: severity·쉬운 문장·위치 라벨(“2주차 · 활동 제목”). 린트 코드(W1xx 등)는 노출하지 않는다.
"""

from __future__ import annotations

import re
from typing import Any

from ..lint import Finding, lint
from ..spec import SpecError, from_data
from .errors import WebError

KIND_LABELS = {
    "page": "읽기",
    "file": "자료",
    "quiz": "퀴즈",
    "discussion": "토론",
    "assignment": "과제",
    "peer_review": "동료평가",
    "wiki": "위키",
    "glossary": "용어",
    "survey": "설문",
    "h5p": "H5P",
    "interactive_lecture": "수업",
}

LEVEL_LABELS = {
    "remember": "기억",
    "understand": "이해",
    "apply": "적용",
    "analyze": "분석",
    "evaluate": "평가",
    "create": "창안",
}

_WEEK_PREFIX = re.compile(r"^\s*\d{1,2}\s*주차\s*[—–:\-]?\s*")


def load_checked(data: Any, path: Any = None):
    """스키마 검증을 통과한 Spec 을 돌려준다. 실패하면 쉬운 한국어 WebError."""
    try:
        return from_data(data, path)
    except SpecError:
        raise WebError("설계서 형식에 문제가 있어 화면에 보여드릴 수 없습니다.", status=500) from None


def _strip_week_prefix(title: str) -> str:
    return _WEEK_PREFIX.sub("", title or "").strip() or (title or "")


def _where_label(finding: Finding, spec) -> str:
    """린트 위치(id)를 교수가 읽는 라벨(“2주차 · 확인 퀴즈”)로 바꾼다."""
    where = finding.where
    if where in spec.unit_index:
        return f"{spec.unit_index[where] + 1}주차"
    if where in spec.unit_of:
        unit = spec.units[spec.unit_index[spec.unit_of[where]]]
        return f"{spec.unit_index[unit['id']] + 1}주차 · {(spec.items[where].get('title') or '활동')}"
    for i, outcome in enumerate(spec.outcomes, 1):
        if outcome.get("id") == where:
            return f"학습목표 {i}"
    for badge in spec.badges:
        if badge.get("id") == where:
            return f"배지 · {badge.get('name') or where}"
    if where == "grading":
        return "평가 비중"
    return "과정 전체"


def _grading_chip(categories: list[dict[str, Any]]) -> str:
    ordered = sorted(categories, key=lambda c: -c.get("weight", 0))
    return " · ".join(f"{c.get('name', '')} {c.get('weight', 0):g}%" for c in ordered)


def _hours_label(minutes: int | None) -> str:
    if not minutes:
        return ""
    if minutes % 60 == 0:
        return f"{minutes // 60}시간"
    return f"{minutes}분"


def build_map(design_id: str, data: dict, path: Any = None, confirmed: bool = False) -> dict:
    """설계서 dict 를 화면 03 에 맞는 화면 모델로 바꾼다."""
    spec = load_checked(data, path)
    findings = lint(spec)

    notices = [
        {
            "severity": "error" if f.is_error else "warning",
            "message": f.message,
            "where": _where_label(f, spec),
        }
        for f in findings
    ]
    can_confirm = not any(f.is_error for f in findings)

    workload = spec.data.get("policies", {}).get("workload", {})
    max_minutes = workload.get("max_minutes_per_unit")

    units = []
    for i, unit in enumerate(spec.units, 1):
        items = []
        for item in unit.get("items", []):
            due_day = item.get("due_day")
            note = None
            if item.get("type") == "interactive_lecture":
                note = "오픈마익"
            elif item.get("type") == "survey" and item.get("survey", {}).get("anonymous"):
                note = "익명"
            items.append(
                {
                    "id": item.get("id", ""),
                    "kind": KIND_LABELS.get(item.get("type", ""), item.get("type", "")),
                    "title": item.get("title", ""),
                    "minutes": item.get("estimated_minutes", 0),
                    "due_day": due_day,
                    "due_label": f"{due_day}일차 마감" if due_day else None,
                    "note": note,
                }
            )
        units.append(
            {
                "id": unit.get("id", ""),
                "index": i,
                "title": _strip_week_prefix(unit.get("title", "")),
                "summary": unit.get("summary", "") or "",
                "total_minutes": sum(it.get("estimated_minutes", 0) for it in unit.get("items", [])),
                "items": items,
            }
        )

    outcomes = [
        {
            "index": i,
            "label": f"목표 {i} · {LEVEL_LABELS.get(o.get('level', ''), o.get('level', ''))}".rstrip(" ·"),
            "statement": o.get("statement", ""),
            "level": LEVEL_LABELS.get(o.get("level", ""), o.get("level", "")),
        }
        for i, o in enumerate(spec.outcomes, 1)
    ]

    return {
        "design_id": design_id,
        "title": spec.title,
        "confirmed": confirmed,
        "can_confirm": can_confirm,
        "summary": {
            "unit_count": len(units),
            "outcome_count": len(outcomes),
            "grading": _grading_chip(spec.categories),
            "max_per_unit_label": _hours_label(max_minutes),
        },
        "outcomes": outcomes,
        "units": units,
        "notices": notices,
    }
