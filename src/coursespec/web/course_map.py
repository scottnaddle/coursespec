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

# 린트 코드(E***/W***)별 교수에게 보여 줄 쉬운 한국어 문장.
# 스펙 키 이름(requires·grading·rights.license 등), 원시 id('w2-quiz' 같은), 영문 단어를
# 절대 넣지 않는다. 코드가 사전에 없으면 _GENERIC_NOTICE 로 돌린다.
_FRIENDLY_MESSAGES: dict[str, str] = {
    "E001": "같은 이름을 쓰는 항목이 여러 개 있습니다. 겹치는 이름을 서로 다르게 바꿔 주세요.",
    "E002": "연결된 학습목표 중에 목록에 없는 것이 있습니다. 활동에 연결된 목표를 확인해 주세요.",
    "E003": "앞서 해야 할 활동으로 지목한 활동을 찾지 못했습니다. 앞 주차에 있는 활동인지 확인해 주세요.",
    "E004": "앞서 해야 할 활동이 서로를 가리켜 순환합니다. 순서를 한쪽 방향으로만 정리해 주세요.",
    "E005": "평가 활동이 과정에 없는 평가 항목에 연결돼 있습니다. 연결된 평가 항목을 확인해 주세요.",
    "E006": "배지를 받을 조건으로 걸어둔 활동을 찾지 못했습니다. 조건의 활동 이름을 확인해 주세요.",
    "E007": "마감일이 공개일보다 앞서 있습니다. 날짜를 다시 확인해 주세요.",
    "E008": "완료 기준에 필요한 점수 설정이 빠졌거나 잘못됐습니다. 점수 설정을 확인해 주세요.",
    "E009": "퀴즈 문항에 필요한 보기나 정답이 빠져 있습니다. 문항을 확인해 주세요.",
    "E010": "평가 기준표의 점수 단계가 겹칩니다. 각 단계의 점수를 서로 다르게 정해 주세요.",
    "E011": "활동 종류와 맞지 않는 완료 기준이 걸려 있습니다. 완료 기준을 확인해 주세요.",
    "E012": "활동 이름이 너무 길어 학습 관리 시스템에 넣지 못합니다. 이름을 줄여 주세요.",
    "E013": "평가 항목에 비중(백분율)이 빠져 있습니다. 비중을 적어 주세요.",
    "E014": "실시간 수업 활동에 수업 안내 문장이 빠져 있습니다. 안내 문장을 적어 주세요.",
    "E015": "활동에 연결된 자료가 자료 목록에 없습니다. 자료를 다시 연결해 주세요.",
    "E016": "자료에 연결된 주차를 찾지 못했습니다. 자료가 속한 주차를 확인해 주세요.",
    "E017": "학습자에게 공개할 수 없는 자료가 활동에 연결돼 있습니다. 자료의 공개 설정을 확인해 주세요.",
    "W101": "이 학습목표를 평가하는 활동이 없습니다. 평가 활동을 하나 연결해 주세요.",
    "W102": "이 학습목표를 다루는 활동이 없습니다. 활동에 이 목표를 연결해 주세요.",
    "W103": "평가 활동에 학습목표가 연결돼 있지 않습니다. 목표를 연결해 주세요.",
    "W104": "평가 비중의 합이 100%가 아닙니다. 각 항목의 비중을 확인해 주세요.",
    "W105": "이 주차의 예상 학습 시간이 미리 정한 한도를 넘습니다. 시간을 조절해 주세요.",
    "W106": "같은 주차나 뒤 주차의 활동을 앞서 해야 할 활동으로 걸 수 없습니다. 앞 주차 활동으로 바꿔 주세요.",
    "W107": "문항이 없는 퀴즈입니다. 문항을 넣어 주세요.",
    "W108": "배지 조건의 활동에 완료 기준이 없어 배지가 주어지지 않습니다. 완료 기준을 정해 주세요.",
    "W109": "평가 항목이 정해지지 않은 평가 활동이 있습니다. 어느 항목으로 평가할지 정해 주세요.",
    "W110": "이 종류의 활동에 둔 평가 기준표는 쓰이지 않습니다.",
    "W111": "수업에서 쓸 자료가 콘텐츠 생성용으로 표시되지 않았습니다. 자료 설정을 확인해 주세요.",
    "W112": "자료의 이용 권한(라이선스)이 확인되지 않았습니다. 자료의 권한 정보를 확인해 주세요.",
    "W113": "이 학습목표를 다루는 튜터용 자료가 없습니다.",
    "W115": "만든 수업의 남은 기록이 없어 버전 관리되지 않습니다.",
}
_GENERIC_NOTICE = "설계에서 확인이 필요한 부분이 있습니다."


def _friendly_message(finding: Finding) -> str:
    """린트 원문(코드·스펙 키·원시 id 들어감) 대신 교수에게 보여 줄 쉬운 문장."""
    return _FRIENDLY_MESSAGES.get(finding.code, _GENERIC_NOTICE)


def load_checked(data: Any, path: Any = None):
    """스키마 검증을 통과한 Spec 을 돌려준다. 실패하면 쉬운 한국어 WebError."""
    try:
        return from_data(data, path)
    except SpecError:
        raise WebError("설계서 형식에 문제가 있어 화면에 보여드릴 수 없습니다.", status=500) from None


def _strip_week_prefix(title: str) -> str:
    return _WEEK_PREFIX.sub("", title or "").strip() or (title or "")


def _where_label(finding: Finding, spec) -> str:
    """린트 위치(id)를 교수가 읽는 라벨(“2주차 · 확인 퀴즈”)로 바꾼다. 원시 id 는 노출하지 않는다."""
    where = finding.where.split("#", 1)[0]  # 문항 위치는 활동 기준으로 돌린다
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
            return f"배지 · {badge.get('name') or '배지'}"
    if where in spec.materials:
        return f"자료 · {(spec.materials[where].get('title') or '자료')}"
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
            "message": _friendly_message(f),
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
