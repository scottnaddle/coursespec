"""Canvas 퍼블리셔: 설계서 → Canvas REST API 호출 계획 (초안).

Canvas 는 아직 공식 MCP 가 일반 출시되지 않았으므로 REST API v1 과 New Quizzes API 를 직접 대상으로 한다.
공식 MCP 가 나오면 이 모듈의 단계만 그 도구 호출로 바꾸면 된다 (설계서와 린트는 그대로).

단계의 tool 은 다음 둘 중 하나다.
  canvas_request      {method, path, json}  — 일반 REST 호출
  canvas_upload_file  {course_id, source, filename, folder} — Canvas 3단계 파일 업로드를 실행기가 처리

verify=True 인 단계는 형식을 실제 Canvas 인스턴스에서 아직 검증하지 않은 것이다 (docs/lms-mapping.md).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..plan import Plan
from ..render import to_html
from ..spec import Spec
from ..timeline import Timeline
from .moodle import file_source, ref

SUBMISSION = {"text": "online_text_entry", "file": "online_upload"}
SCORE_TO_KEEP = {"highest": "highest", "average": "average", "first": "first", "last": "latest"}
COMPLETION = {
    "view": "must_view",
    "submit": "must_submit",
    "grade": "must_submit",
    "pass": "min_score",
    "posts": "must_contribute",
    "manual": "must_mark_done",
}
SKIPPED = {
    "survey": "Canvas 코어에는 Moodle 피드백 같은 설문 활동이 없어 배포에서 제외합니다.",
    "h5p": "Canvas 에서 H5P 는 LTI 도구로만 쓸 수 있어 배포에서 제외합니다.",
    "interactive_lecture": "인터랙티브 강의(OpenMAIC)는 Canvas 대응이 없고 내보내기(lecture.exports)도 없어 배포에서 제외합니다.",
}


def api(course: Any, tail: str) -> str:
    return f"/api/v1/courses/{course}{tail}"


def plan_canvas(spec: Spec, start: date, course_id: int | None = None, account_id: int | None = None) -> Plan:
    tl = Timeline(start, spec.timezone)
    plan = Plan("canvas", spec.id, spec.data.get("version"), start.isoformat())
    req = lambda method, path, body, about, **kw: plan.add(  # noqa: E731
        "canvas_request", {"method": method, "path": path, "json": body}, about, **kw
    )

    plan.note("course", "info", "모든 과제·페이지·토론은 미게시 상태로 만들어집니다. 교수자가 검토 후 게시하세요.")

    # 1. 강좌
    if course_id is None:
        if account_id is None:
            raise ValueError("새 Canvas 강좌를 만들려면 account_id 가 필요합니다 (또는 기존 course_id 지정).")
        req("POST", f"/api/v1/accounts/{account_id}/courses",
            {"course": {"name": spec.data["title"], "course_code": spec.data.get("shortname", spec.id),
                        "start_at": tl.iso(1), "time_zone": spec.timezone, "default_view": "modules",
                        "public_description": spec.data.get("summary", "")}},
            "강좌 생성", binds={"course.id": "id"})  # fmt: skip
        course: Any = ref("course.id")
    else:
        course = course_id

    # 2. 성적 카테고리 → 과제 그룹
    agg = spec.data.get("grading", {}).get("aggregation", "weighted_mean")
    for cat in spec.categories:
        req("POST", api(course, "/assignment_groups"), {"name": cat["name"], "group_weight": cat.get("weight", 0)},
            f"과제 그룹: {cat['name']}", binds={f"cat.{cat['id']}": "id"})  # fmt: skip
    if spec.categories:
        if agg == "mean":
            plan.note("grading", "warn", "Canvas 에는 카테고리 단순 평균 집계가 없어 가중치 없이 점수 합산으로 계산됩니다.")
        else:
            req("PUT", api(course, ""), {"course": {"apply_assignment_group_weights": True}}, "과제 그룹 가중치 적용")

    # 3. 모듈 (단원)
    for pos, unit in enumerate(spec.units, 1):
        req("POST", api(course, "/modules"),
            {"module": {"name": unit["title"], "position": pos, "unlock_at": tl.iso(unit.get("opens_day"))}},
            f"모듈 {pos}: {unit['title']}", binds={f"{unit['id']}.module": "id"})  # fmt: skip
        if unit.get("summary"):
            plan.note(unit["id"], "info", "Canvas 모듈에는 요약 필드가 없어 단원 요약은 배포되지 않습니다.")

    # 4. 활동과 모듈 아이템
    deployed: set[str] = set()
    for _, unit, item in spec.iter_items():
        if _plan_item(plan, spec, tl, course, unit, item):
            deployed.add(item["id"])

    # 5. 선수조건: Canvas 는 모듈 단위로만 가능하다
    _plan_prerequisites(plan, spec, course, deployed)

    for badge in spec.badges:
        plan.note(badge["id"], "loss", "Canvas 코어에는 배지가 없습니다 (별도 제품 Canvas Credentials). 배포에서 제외합니다.")
    for b in spec.badges:
        for r in b["criteria"].get("items", []):
            if r not in deployed and r in spec.items:
                plan.note(b["id"], "info", f"배지 조건 '{r}'도 Canvas 에 배포되지 않습니다.")
    return plan


def _plan_item(plan: Plan, spec: Spec, tl: Timeline, course: Any, unit: dict[str, Any], item: dict[str, Any]) -> bool:
    iid, itype = item["id"], item["type"]
    exports = item.get("lecture", {}).get("exports", {})
    if itype == "interactive_lecture" and (exports.get("html") or exports.get("video")):
        return _plan_lecture_export(plan, course, unit, item, exports)
    if itype in SKIPPED:
        plan.note(iid, "loss", SKIPPED[itype])
        return False

    req = lambda method, path, body, about, **kw: plan.add(  # noqa: E731
        "canvas_request", {"method": method, "path": path, "json": body}, about, **kw
    )
    grading = item.get("grading", {})
    group = ref(f"cat.{grading['category']}") if grading.get("category") else None
    intro = to_html(item.get("intro"))
    dates = {"unlock_at": tl.iso(item.get("opens_day")), "due_at": tl.iso(item.get("due_day"), True),
             "lock_at": tl.iso(item.get("cutoff_day"), True)}  # fmt: skip
    module_item: dict[str, Any] = {"title": item["title"]}

    if itype in ("page", "wiki"):
        body = to_html(item.get("content"), item.get("content_format", "markdown")) if itype == "page" else intro
        if item.get("video_url"):
            body += f'<p><a href="{item["video_url"]}">동영상 보기</a></p>'
            plan.note(iid, "info", "동영상은 링크로 넣습니다. 임베드는 Canvas 편집기에서 바꿀 수 있습니다.")
        page: dict[str, Any] = {"title": item["title"], "body": body, "published": False}
        if itype == "wiki":
            page["editing_roles"] = "teachers,students"
            plan.note(iid, "warn", "위키는 학생도 편집할 수 있는 Canvas 페이지로 바뀝니다. 개인 위키(individual)와 페이지 이력 기능은 다릅니다.")
        req("POST", api(course, "/pages"), {"wiki_page": page}, f"{itype}: {item['title']}", binds={f"{iid}.page_url": "url"})
        module_item.update(type="Page", page_url=ref(f"{iid}.page_url"))
        if item.get("opens_day"):
            plan.note(iid, "warn", "Canvas 페이지는 개별 공개일이 없어 모듈 공개일만 적용됩니다.")
    elif itype == "file":
        source = file_source(spec, item)
        plan.add("canvas_upload_file",
                 {"course_id": course, "source": source,
                  "filename": item.get("filename") or source.rsplit("/", 1)[-1], "folder": "coursespec"},
                 f"파일 업로드: {item['title']}", binds={f"{iid}.file_id": "id"})  # fmt: skip
        module_item.update(type="File", content_id=ref(f"{iid}.file_id"))
    elif itype in ("assignment", "peer_review"):
        sub = item.get("submission", {})
        a: dict[str, Any] = {"name": item["title"], "description": intro, "points_possible": grading.get("max", 0),
                             "submission_types": [SUBMISSION[t] for t in sub.get("types", ["text"])],
                             "assignment_group_id": group, "published": False, **dates}  # fmt: skip
        if itype == "peer_review":
            a.update(peer_reviews=True, automatic_peer_reviews=True)
            pr = item.get("peer_review", {})
            if pr.get("assessment_max"):
                plan.note(iid, "loss", "Canvas 동료 검토는 평가 활동 자체에 점수를 주지 않습니다 (Moodle 워크숍의 평가 점수 손실).")
            if pr.get("assessment_due_day"):
                plan.note(iid, "warn", "동료 평가 마감일은 Canvas 에서 별도로 지정할 수 없어 과제 마감 기준으로 운영됩니다.")
        a = {k: v for k, v in a.items() if v is not None}
        req("POST", api(course, "/assignments"), {"assignment": a}, f"{itype}: {item['title']}", binds={f"{iid}.id": "id"})
        if sub.get("max_files"):
            plan.note(iid, "info", "Canvas 과제는 업로드 파일 수 제한이 없습니다.")
        if "rubric" in item:
            req("POST", api(course, "/rubrics"), _rubric(item["rubric"], ref(f"{iid}.id")), f"루브릭: {iid}", verify=True)
        module_item.update(type="Assignment", content_id=ref(f"{iid}.id"))
    elif itype == "quiz":
        q = item.get("quiz", {})
        settings: dict[str, Any] = {}
        if "time_limit_minutes" in q:
            settings.update(has_time_limit=True, session_time_limit_in_seconds=q["time_limit_minutes"] * 60)
        attempts = q.get("attempts", 0)
        if attempts != 1:
            settings["multiple_attempts"] = {
                "multiple_attempts_enabled": True,
                "attempt_limit": attempts > 0,
                "max_attempts": attempts or None,
                "score_to_keep": SCORE_TO_KEEP[q.get("grade_method", "highest")],
            }
        body = {"title": item["title"], "instructions": intro, "points_possible": grading.get("max", 10),
                "assignment_group_id": group, **dates, "quiz_settings": settings}  # fmt: skip
        plan.add("canvas_request",
                 {"method": "POST", "path": f"/api/quiz/v1/courses/{course}/quizzes",
                  "json": {"quiz": {k: v for k, v in body.items() if v is not None}}},
                 f"New Quiz: {item['title']}", binds={f"{iid}.id": "id"}, verify=True)  # fmt: skip
        for pos, question in enumerate(item.get("questions", []), 1):
            plan.add("canvas_request",
                     {"method": "POST", "path": f"/api/quiz/v1/courses/{course}/quizzes/{ref(iid + '.id')}/items",
                      "json": {"item": _quiz_item(plan, iid, pos, question)}},
                     f"문항 {pos}: {iid}", verify=True)  # fmt: skip
        module_item.update(type="Assignment", content_id=ref(f"{iid}.id"))
    elif itype in ("discussion", "glossary"):
        topic: dict[str, Any] = {"title": item["title"], "message": intro, "discussion_type": "threaded", "published": False}
        if item.get("discussion", {}).get("style") == "qanda":
            topic["require_initial_post"] = True
        if grading:
            topic["assignment"] = {k: v for k, v in {"points_possible": grading["max"], "assignment_group_id": group,
                                                     "due_at": dates["due_at"]}.items() if v is not None}  # fmt: skip
        if itype == "glossary":
            plan.note(iid, "warn", "용어집은 Canvas 토론으로 바뀝니다. 항목 승인·자동 링크 기능은 없습니다.")
        req("POST", api(course, "/discussion_topics"), topic, f"{itype}: {item['title']}", binds={f"{iid}.id": "id"})
        module_item.update(type="Discussion", content_id=ref(f"{iid}.id"))
    else:  # pragma: no cover
        raise ValueError(itype)

    completion = item.get("completion", {"mode": "none"})
    mode = completion["mode"]
    if mode in COMPLETION:
        cr: dict[str, Any] = {"type": COMPLETION[mode]}
        if mode == "pass":
            cr["min_score"] = completion.get("pass_grade", 0)
        if mode == "grade":
            plan.note(iid, "warn", "Canvas 에는 '성적을 받으면 완료'가 없어 '제출하면 완료'로 바꿉니다.")
        if mode == "posts" and completion.get("posts", 1) > 1:
            plan.note(iid, "warn", f"Canvas 는 게시글 수({completion['posts']}개) 조건이 없어 '참여하면 완료'로 바꿉니다.")
        module_item["completion_requirement"] = cr
    req("POST", api(course, f"/modules/{ref(unit['id'] + '.module')}/items"), {"module_item": module_item},
        f"모듈 아이템: {iid}", binds={f"{iid}.module_item": "id"})  # fmt: skip
    return True


def _plan_lecture_export(plan: Plan, course: Any, unit: dict[str, Any], item: dict[str, Any], exports: dict[str, str]) -> bool:
    """OpenMAIC 수업을 내보낸 HTML(우선) 또는 동영상 파일로 배포한다."""
    iid = item["id"]
    kind, source = ("html", exports["html"]) if exports.get("html") else ("video", exports["video"])
    plan.add("canvas_upload_file",
             {"course_id": course, "source": source, "filename": source.rsplit("/", 1)[-1], "folder": "coursespec"},
             f"수업 내보내기({kind}) 업로드: {item['title']}", binds={f"{iid}.file_id": "id"})  # fmt: skip
    what = "HTML 페이지" if kind == "html" else "동영상"
    plan.note(iid, "warn", f"인터랙티브 강의를 내보낸 {what}로 배포합니다. AI 교사·급우와의 실시간 상호작용과 AI 채점은 빠집니다.")
    module_item: dict[str, Any] = {"title": item["title"], "type": "File", "content_id": ref(f"{iid}.file_id")}
    if item.get("completion", {}).get("mode", "none") != "none":
        module_item["completion_requirement"] = {"type": "must_view"}
        if item["completion"]["mode"] != "view":
            plan.note(iid, "warn", "내보낸 수업은 '열람하면 완료'로만 추적됩니다.")
    if item.get("grading"):
        plan.note(iid, "loss", "내보낸 수업에는 점수가 없어 성적이 기록되지 않습니다.")
    plan.add("canvas_request",
             {"method": "POST", "path": api(course, f"/modules/{ref(unit['id'] + '.module')}/items"),
              "json": {"module_item": module_item}},
             f"모듈 아이템: {iid}", binds={f"{iid}.module_item": "id"})  # fmt: skip
    return True


def _plan_prerequisites(plan: Plan, spec: Spec, course: Any, deployed: set[str]) -> None:
    prereq: dict[str, set[str]] = {u["id"]: set() for u in spec.units}
    sequential: set[str] = set()
    for unit in spec.units:
        for r in unit.get("requires", []):
            if r in spec.unit_of and spec.unit_of[r] != unit["id"]:
                prereq[unit["id"]].add(spec.unit_of[r])
                plan.note(unit["id"], "warn", f"단원 선수조건('{r}')은 Canvas 에서 모듈 '{spec.unit_of[r]}' 전체 완료 조건으로 넓어집니다.")
        for item in unit.get("items", []):
            for r in item.get("requires", []):
                if r not in spec.unit_of:
                    continue
                src = spec.unit_of[r]
                if src == unit["id"]:
                    sequential.add(unit["id"])
                    plan.note(item["id"], "warn", f"같은 모듈 안의 선수조건('{r}')은 Canvas 에서 '모듈 순서대로 진행'으로 바뀝니다.")
                else:
                    prereq[unit["id"]].add(src)
                    plan.note(item["id"], "warn", f"활동 단위 선수조건('{r}')은 Canvas 에서 모듈 '{src}' 전체 완료 조건으로 넓어집니다.")
                if r not in deployed:
                    plan.note(item["id"], "warn", f"선수 활동 '{r}'이 Canvas 에 배포되지 않습니다.")
                elif spec.items[r].get("completion", {}).get("mode", "none") == "none":
                    plan.note(item["id"], "warn", f"선수 활동 '{r}'에 완료 조건이 없어 Canvas 선수조건이 풀리지 않을 수 있습니다.")
    for unit in spec.units:
        uid = unit["id"]
        mods = sorted(prereq[uid], key=spec.unit_index.get)
        if not mods and uid not in sequential:
            continue
        body: dict[str, Any] = {}
        if mods:
            body["prerequisite_module_ids"] = [ref(f"{m}.module") for m in mods]
        if uid in sequential:
            body["require_sequential_progress"] = True
        plan.add("canvas_request",
                 {"method": "PUT", "path": api(course, f"/modules/{ref(uid + '.module')}"), "json": {"module": body}},
                 f"모듈 선수조건: {uid}")  # fmt: skip


def _rubric(rubric: dict[str, Any], assignment_ref: str) -> dict[str, Any]:
    criteria = {}
    for ci, c in enumerate(rubric["criteria"]):
        levels = sorted(c["levels"], key=lambda lv: -lv["score"])
        criteria[str(ci)] = {
            "description": c["description"],
            "points": levels[0]["score"],
            "ratings": {str(li): {"description": lv["definition"], "points": lv["score"]} for li, lv in enumerate(levels)},
        }
    return {
        "rubric": {"title": rubric["name"], "criteria": criteria},
        "rubric_association": {"association_id": assignment_ref, "association_type": "Assignment",
                               "use_for_grading": True, "purpose": "grading"},
    }  # fmt: skip


def _quiz_item(plan: Plan, iid: str, pos: int, q: dict[str, Any]) -> dict[str, Any]:
    t = q["type"]
    entry: dict[str, Any] = {"title": q.get("name") or f"Q{pos}", "item_body": q["text"]}
    if q.get("feedback"):
        entry["feedback"] = {"neutral": q["feedback"]}
    if t == "multichoice":
        choices = q.get("choices", [])
        ids = [f"c{i}" for i in range(1, len(choices) + 1)]
        entry["interaction_data"] = {
            "choices": [{"id": cid, "position": i, "item_body": c["text"]} for i, (cid, c) in enumerate(zip(ids, choices), 1)]
        }
        correct = [cid for cid, c in zip(ids, choices) if c.get("correct")]
        if q.get("multiple"):
            entry.update(interaction_type_slug="multi-answer", scoring_data={"value": correct}, scoring_algorithm="AllOrNothing")
            plan.note(iid, "warn", f"문항 {pos}: 복수 정답 부분 점수가 Canvas 에서는 전부 맞혀야 점수(AllOrNothing)로 바뀝니다.")
        else:
            entry.update(interaction_type_slug="choice", scoring_data={"value": correct[0] if correct else None},
                         scoring_algorithm="Equivalence")  # fmt: skip
        if any(c.get("feedback") for c in choices):
            plan.note(iid, "info", f"문항 {pos}: 보기별 피드백은 배포되지 않습니다.")
    elif t == "truefalse":
        entry.update(interaction_type_slug="true-false", interaction_data={"true_choice": "참", "false_choice": "거짓"},
                     scoring_data={"value": bool(q["answer"])}, scoring_algorithm="Equivalence")  # fmt: skip
    else:
        if t == "shortanswer":
            plan.note(iid, "loss", f"문항 {pos}: 단답형은 서술형(수동 채점)으로 바뀌어 자동 채점이 사라집니다.")
        entry.update(interaction_type_slug="essay", interaction_data={"rce": True, "word_count": False},
                     scoring_data={"value": q.get("grader_info", "")}, scoring_algorithm="None")  # fmt: skip
    return {"position": pos, "points_possible": q.get("mark", 1), "entry_type": "Item", "entry": entry}
