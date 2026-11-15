"""튜터 팩: 설계서에서 학습자 튜터(DeepTutor 등)용 강좌 설정을 만든다.

튜터 팩은 특정 튜터 제품에 묶이지 않는 JSON(tutor-pack.json)과, 에이전트 스킬 형식의
지시문(SKILL.md)으로 구성된다. 학생 데이터는 들어가지 않는다. 운영 중 튜터가 Moodle 에서 받은
학습자 본인의 기록은 `external_id`(활동 ID number)로 이 팩의 학습목표 지도에 연결된다.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .spec import Spec
from .timeline import Timeline

GRADED_TYPES = {"assignment", "quiz", "peer_review", "discussion"}


def integrity_rules(spec: Spec, start: date | None = None) -> list[dict[str, Any]]:
    """채점 대상 활동이 열려 있는 동안 튜터는 답이 아닌 힌트만 준다."""
    tl = Timeline(start, spec.timezone) if start else None
    rules = []
    for _, unit, item in spec.iter_items():
        if item["type"] not in GRADED_TYPES or not item.get("grading"):
            continue
        frm = item.get("opens_day") or unit.get("opens_day") or 1
        until = item.get("cutoff_day") or item.get("due_day")
        if item["type"] == "peer_review":
            until = item.get("peer_review", {}).get("assessment_due_day") or until
        rule: dict[str, Any] = {
            "item": item["id"],
            "external_id": spec.external_id(item["id"]),
            "title": item["title"],
            "mode": "no_ghostwriting" if item["type"] == "discussion" else "hint_only",
            "from_day": frm,
            "until_day": until,
        }
        if tl:
            rule["from"] = tl.iso(frm)
            rule["until"] = tl.iso(until, True) if until else None
        rules.append(rule)
    return rules


def tutor_pack(spec: Spec, start: date | None = None) -> dict[str, Any]:
    outcome_items: dict[str, list[str]] = {o["id"]: [] for o in spec.outcomes}
    question_map: dict[str, list[str]] = {}
    units = []
    for _, unit, item in spec.iter_items():
        for o in item.get("outcomes", []):
            outcome_items.setdefault(o, []).append(item["id"])
        for qi, q in enumerate(item.get("questions", []), 1):
            refs = q.get("outcomes") or item.get("outcomes", [])
            if refs:
                question_map[f"{spec.external_id(item['id'])}#q{qi}"] = refs
    for unit in spec.units:
        units.append({
            "id": unit["id"],
            "title": unit["title"],
            "opens_day": unit.get("opens_day", 1),
            "items": [
                {"id": it["id"], "external_id": spec.external_id(it["id"]), "type": it["type"], "title": it["title"],
                 "outcomes": it.get("outcomes", []), "graded": bool(it.get("grading"))}
                for it in unit.get("items", [])
            ],
        })  # fmt: skip

    return {
        "tutor_pack": "0.1",
        "coursespec": {"id": spec.id, "version": spec.data.get("version")},
        "course": {"title": spec.title, "language": spec.data.get("language", "ko"), "summary": spec.data.get("summary", "")},
        "start": start.isoformat() if start else None,
        "outcomes": [
            {**{k: o[k] for k in ("id", "statement", "level") if k in o}, "items": outcome_items.get(o["id"], [])}
            for o in spec.outcomes
        ],
        "units": units,
        "materials": [
            {k: m[k] for k in ("id", "title", "kind", "source", "sha256", "units", "outcomes", "language") if k in m}
            for m in spec.materials.values()
            if "tutor" in m.get("uses", [])
        ],
        "integrity": integrity_rules(spec, start),
        "mapping": {"external_id_prefix": f"cs:{spec.id}:", "question_outcomes": question_map},
    }


def skill_md(spec: Spec, pack: dict[str, Any]) -> str:
    """튜터용 SKILL.md. 에이전트 스킬 형식(name·description 프런트매터 + 지시문)."""
    lines = [
        "---",
        f"name: tutor-{spec.id}",
        f"description: '{spec.title}' 과정의 학습자 튜터. 이 과정의 학습목표와 자료에 근거해 설명하고, "
        "채점 활동이 열려 있는 동안에는 답 대신 힌트만 준다.",
        "---",
        "",
        f"# {spec.title} 튜터",
        "",
        "당신은 이 과정을 듣는 학습자의 튜터입니다. 교수자가 설계한 학습목표를 기준으로 돕습니다.",
        "",
        "## 학습목표",
    ]
    for o in pack["outcomes"]:
        lines.append(f"- `{o['id']}` {o['statement']}")
    lines += [
        "",
        "## 근거 자료",
        "설명은 지식베이스에 들어 있는 아래 자료를 우선 근거로 하고, 자료에 없는 내용은 그렇다고 밝힙니다.",
    ]
    lines += [f"- {m['title']}" for m in pack["materials"]] or ["- (튜터용 자료가 지정되지 않았습니다)"]
    lines += [
        "",
        "## 학업 정직성 규칙",
        "아래 채점 활동이 열려 있는 기간에는 정답·완성된 답안·채점 기준에 맞춘 대필을 제공하지 않습니다. "
        "개념 설명, 질문으로 생각을 이끄는 힌트, 학습자가 쓴 초안에 대한 방향 피드백은 괜찮습니다.",
    ]
    for r in pack["integrity"]:
        window = f"{r['from_day']}일차부터" + (f" {r['until_day']}일차까지" if r["until_day"] else " 과정 끝까지")
        rule = "게시글 대필 금지, 생각 정리는 도움" if r["mode"] == "no_ghostwriting" else "힌트만"
        lines.append(f"- {r['title']} (`{r['external_id']}`): {window} — {rule}")
    lines += [
        "",
        "## 학습자 기록 해석",
        "학습자 본인의 퀴즈·과제 기록을 받으면, 활동 ID number(`" + pack["mapping"]["external_id_prefix"] + "…`)와 "
        "문항 번호로 이 과정의 학습목표에 연결해 약점을 해석합니다. 다른 학습자의 정보는 요청하거나 언급하지 않습니다.",
        "",
    ]
    return "\n".join(lines)
