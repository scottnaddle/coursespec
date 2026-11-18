"""인계(handoff): 확정·수정된 실라버스 필드를 설계 에이전트용 강의계획서 텍스트로 변환.

`skills/design-agent/SKILL.md` 는 "어느 정도 짜인 강의계획서 텍스트"를 입력으로 전제한다.
교수가 고친 과정 이름, 소개, 학습목표, 주차 제목·요약, 평가 비중이 그대로 들어가야 한다.
이 단계에서 설계서를 자동 생성하거나 `coursespec plan` 을 실행하거나 LMS 를 호출하지 않는다.
"""

from __future__ import annotations


def draft_to_syllabus(draft: dict) -> str:
    """초안 dict 를 설계 에이전트가 읽는 강의계획서 텍스트로 바꾼다."""
    lines: list[str] = []

    title = (draft.get("title") or "").strip() or "이름 없는 과정"
    intro = (draft.get("intro") or "").strip()
    outcomes = draft.get("outcomes") or []
    weeks = draft.get("weeks") or []
    grading = draft.get("grading") or []

    lines.append(f"# {title}")
    lines.append("")

    lines.append("## 과정 개요")
    lines.append("")
    lines.append(intro or f"{title}의 핵심을 다루는 과정입니다.")
    lines.append("")

    if outcomes:
        lines.append("## 학습목표")
        lines.append("")
        for i, outcome in enumerate(outcomes, 1):
            lines.append(f"{i}. {(outcome or '').strip()}")
        lines.append("")

    for i, week in enumerate(weeks, 1):
        week_title = (week.get("title") or "").strip() or f"{i}주차"
        week_summary = (week.get("summary") or "").strip()
        lines.append(f"## {i}주차 — {week_title}")
        lines.append("")
        if week_summary:
            lines.append(week_summary)
        lines.append("")

    if grading:
        lines.append("## 평가")
        lines.append("")
        for item in grading:
            name = (item.get("name") or "").strip()
            weight = item.get("weight")
            lines.append(f"- {name}: {weight}%")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"
