"""Moodle 퍼블리셔: 설계서 → moodle-agent-mcp 도구 호출 계획.

도구 이름과 인자는 moodle-agent-mcp(도구 39개)의 시그니처를 그대로 따른다.
모든 쓰기 도구는 실행기가 먼저 confirm=false 로 미리보기를 받고, 교수자가 계획 전체를 승인한 뒤
confirm=true 로 실행하는 것을 전제로 한다. 그래서 계획의 args 에는 confirm 이 들어 있지 않다.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..plan import Plan
from ..render import to_html
from ..spec import Spec
from ..timeline import Timeline

GRADE_METHOD = {"highest": 1, "average": 2, "first": 3, "last": 4}
SUBMISSION = {"text": "onlinetext", "file": "file"}

# create_* 도구 중 settings 를 받지 않는 것: ID number 를 update_activity 로 따로 심는다.
NO_SETTINGS_TOOLS = {"create_page", "create_resource", "create_assignment", "create_quiz", "create_forum"}


def ref(name: str) -> str:
    return "${" + name + "}"


def plan_moodle(
    spec: Spec,
    start: date,
    course_id: int | None = None,
    category_id: int = 1,
) -> Plan:
    tl = Timeline(start, spec.timezone)
    plan = Plan("moodle", spec.id, spec.data.get("version"), start.isoformat())
    course = course_id if course_id is not None else ref("course.id")

    # 1. 강좌와 섹션
    if course_id is None:
        plan.add(
            "create_course",
            {
                "fullname": spec.data["title"],
                "shortname": spec.data.get("shortname", spec.id),
                "categoryid": category_id,
                "format": "topics",
                "numsections": len(spec.units),
                "startdate": tl.unix(1),
                "summary": to_html(spec.data.get("summary")),
            },
            "강좌 생성",
            binds={"course.id": "courseid"},
        )
        section_of = {u["id"]: i + 1 for i, u in enumerate(spec.units)}
        for unit in spec.units:
            plan.add(
                "update_section",
                {"course_id": course, "section": section_of[unit["id"]], "name": unit["title"],
                 "summary": to_html(unit.get("summary"))},
                f"섹션 {section_of[unit['id']]} 이름·요약: {unit['title']}",
            )  # fmt: skip
        plan.note("course", "info", "강좌의 '이수 추적'이 켜져 있어야 완료 조건이 동작합니다 (create_course 는 사이트 기본값을 따름).")
    else:
        binds = {f"{u['id']}.section": f"sections.{i}.section" for i, u in enumerate(spec.units)}
        plan.add(
            "add_sections",
            {"course_id": course, "names": [u["title"] for u in spec.units],
             "summaries": [to_html(u.get("summary")) for u in spec.units]},
            f"기존 강좌 {course_id}에 섹션 {len(spec.units)}개 추가",
            binds=binds,
        )  # fmt: skip
        section_of = {u["id"]: ref(f"{u['id']}.section") for u in spec.units}

    # 2. 활동
    for _, unit, item in spec.iter_items():
        _plan_item(plan, spec, tl, course, section_of[unit["id"]], item)

    # 3. 접근 제한 (모든 활동이 만들어진 뒤라야 cmid 를 참조할 수 있다)
    for _, unit, item in spec.iter_items():
        req = item.get("requires", [])
        if req or item.get("opens_day"):
            plan.add(
                "set_access_restriction",
                {"target_type": "activity", "course_id": course, "target": ref(f"{item['id']}.cmid"),
                 "required_cmids": [ref(f"{r}.cmid") for r in req], "open_from": tl.unix(item.get("opens_day"))},
                f"접근 제한: {item['id']}",
            )  # fmt: skip
    for unit in spec.units:
        req = unit.get("requires", [])
        if req or unit.get("opens_day"):
            plan.add(
                "set_access_restriction",
                {"target_type": "section", "course_id": course, "target": section_of[unit["id"]],
                 "required_cmids": [ref(f"{r}.cmid") for r in req], "open_from": tl.unix(unit.get("opens_day"))},
                f"섹션 접근 제한: {unit['id']}",
            )  # fmt: skip

    # 4. 성적부
    if spec.categories:
        members: dict[str, list[str]] = {c["id"]: [] for c in spec.categories}
        for _, _, item in spec.iter_items():
            cat = item.get("grading", {}).get("category")
            if cat in members:
                members[cat].append(ref(f"{item['id']}.cmid"))
        plan.add(
            "set_grade_categories",
            {"course_id": course, "aggregation": spec.data["grading"].get("aggregation", "weighted_mean"),
             "categories": [{"name": c["name"], "weight": c.get("weight"), "cmids": members[c["id"]]}
                            for c in spec.categories]},
            "성적 카테고리와 가중치",
        )  # fmt: skip

    # 5. 배지 (비활성 상태로 만든다. 활성화는 교수자가 확인 후)
    for badge in spec.badges:
        crit = badge["criteria"]
        plan.add(
            "create_badge",
            {"course_id": course, "name": badge["name"], "description": badge["description"],
             "activity_cmids": [ref(f"{r}.cmid") for r in crit.get("items", [])],
             "min_course_grade": crit.get("min_course_grade"), "enable": False},
            f"배지: {badge['name']} (비활성으로 생성)",
        )  # fmt: skip
        if "min_course_grade" in crit:
            plan.note(badge["id"], "warn", "과정 성적 기준 배지는 Moodle 강좌 이수 설정이 되어 있어야 동작합니다.")

    return plan


def _plan_item(plan: Plan, spec: Spec, tl: Timeline, course: Any, section: Any, item: dict[str, Any]) -> None:
    iid, itype = item["id"], item["type"]
    completion = item.get("completion", {"mode": "none"})
    mode = completion["mode"]
    grading = item.get("grading", {})
    base = {
        "course_id": course,
        "section": section,
        "name": item["title"],
        "intro": to_html(item.get("intro")),
        "visible": 1 if item.get("visible", True) else 0,
    }
    ext = item.get("extensions", {}).get("moodle", {}).get("settings", {})
    settings = {"cmidnumber": spec.external_id(iid), **ext}
    handled = {"none"}  # 생성 도구가 직접 처리하는 완료 조건
    tool: str
    args: dict[str, Any]

    if itype == "page":
        tool = "create_page"
        args = {**base, "content_html": to_html(item.get("content"), item.get("content_format", "markdown")),
                "video_url": item.get("video_url"), "completion_view": mode == "view"}  # fmt: skip
        handled.add("view")
    elif itype == "file":
        source = file_source(spec, item)
        tool = "create_resource"
        args = {**base, "filename": item.get("filename") or source.rsplit("/", 1)[-1],
                "completion_view": mode == "view", **_file_source(plan, iid, source)}  # fmt: skip
        handled.add("view")
    elif itype == "assignment":
        sub = item.get("submission", {})
        tool = "create_assignment"
        args = {**base, "allowsubmissionsfromdate": tl.unix(item.get("opens_day")),
                "duedate": tl.unix(item.get("due_day"), True), "cutoffdate": tl.unix(item.get("cutoff_day"), True),
                "grade": grading.get("max", 100),
                "submission_types": [SUBMISSION[t] for t in sub.get("types", ["text"])],
                "max_files": sub.get("max_files", 1), "completion_submit": mode == "submit"}  # fmt: skip
        handled.add("submit")
    elif itype == "quiz":
        q = item.get("quiz", {})
        tool = "create_quiz"
        args = {**base, "timeopen": tl.unix(item.get("opens_day")), "timeclose": tl.unix(item.get("due_day"), True),
                "timelimit": q["time_limit_minutes"] * 60 if "time_limit_minutes" in q else None,
                "attempts": q.get("attempts", 0), "grademethod": GRADE_METHOD[q.get("grade_method", "highest")],
                "grade": grading.get("max", 10),
                "completion_pass_grade": completion.get("pass_grade") if mode == "pass" else None}  # fmt: skip
        handled.add("pass")
    elif itype == "discussion":
        tool = "create_forum"
        args = {**base, "type": item.get("discussion", {}).get("style", "general"),
                "max_grade": int(grading.get("max", 0)), "duedate": tl.unix(item.get("due_day"), True),
                "completion_posts": completion.get("posts", 1) if mode == "posts" else 0}  # fmt: skip
        if grading and grading["max"] != int(grading["max"]):
            plan.note(iid, "info", "Moodle 포럼 점수는 정수만 받아 만점을 내림했습니다.")
        handled.add("posts")
    elif itype == "peer_review":
        pr = item.get("peer_review", {})
        tool = "create_workshop"
        args = {**base, "strategy": "rubric" if "rubric" in item else "accumulative",
                "grade": grading.get("max", 80), "gradinggrade": pr.get("assessment_max", 20),
                "submission_types": item.get("submission", {}).get("types", ["text", "file"]),
                "submission_start": tl.unix(item.get("opens_day")), "submission_end": tl.unix(item.get("due_day"), True),
                "assessment_end": tl.unix(pr.get("assessment_due_day"), True), "settings": settings}  # fmt: skip
        plan.note(iid, "info", "동료평가는 워크숍으로 배포되며 '설정' 단계에서 시작합니다. 단계 전환은 교수자가 Moodle에서 합니다.")
        if mode == "submit":
            mode = "grade"
            plan.note(iid, "warn", "Moodle 워크숍에는 '제출하면 완료'가 없어 '성적을 받으면 완료'로 바꿉니다.")
    elif itype == "wiki":
        tool = "create_wiki"
        args = {**base, "mode": item.get("wiki", {}).get("mode", "collaborative"),
                "first_page_title": item["title"], "settings": settings}  # fmt: skip
    elif itype == "glossary":
        tool = "create_glossary"
        args = {**base, "settings": settings}
    elif itype == "survey":
        tool = "create_feedback"
        args = {**base, "anonymous": item.get("survey", {}).get("anonymous", True),
                "timeopen": tl.unix(item.get("opens_day")), "timeclose": tl.unix(item.get("due_day"), True),
                "completion_submit": mode == "submit", "settings": settings}  # fmt: skip
        handled.add("submit")
        plan.note(iid, "warn", "설문 문항은 아직 MCP로 추가할 수 없어 빈 피드백 활동이 만들어집니다.")
    elif itype == "h5p":
        tool = "create_h5pactivity"
        args = {**base, "filename": item.get("filename") or item["source"].rsplit("/", 1)[-1],
                "grade": grading.get("max", 100),
                "completion_pass_grade": completion.get("pass_grade") if mode == "pass" else None,
                "completion_view": mode == "view", "settings": settings, **_file_source(plan, iid, item["source"])}  # fmt: skip
        handled |= {"view", "pass"}
    elif itype == "interactive_lecture":
        from .openmaic import requirement

        lec = item.get("lecture", {})
        tool = "create_openmaic"
        args = {**base, "grade": int(grading.get("max", 100)),
                "completion_min_progress": lec.get("min_progress", 80) if mode == "view" else 0,
                "settings": settings}  # fmt: skip
        if lec.get("classroom"):
            args["lecture_id"] = lec["classroom"]["id"]
            plan.note(iid, "info", f"생성해 둔 OpenMAIC 수업({lec['classroom']['id']})을 연결합니다. mod_openmaic 가 같은 OpenMAIC 서버를 써야 합니다.")
        else:
            args["prompt"] = requirement(spec, item)
            plan.note(iid, "warn", "수업이 아직 생성되지 않아 Moodle 활동 페이지에서 생성됩니다. 먼저 `plan --target openmaic` 로 생성·검토하길 권합니다.")
            if lec.get("materials"):
                plan.note(iid, "warn", "이 경로에서는 자료 매니페스트의 자료가 생성에 전달되지 않습니다.")
        handled.add("view")
        plan.note(iid, "warn", "인터랙티브 강의는 Moodle에 mod_openmaic 플러그인이 있어야 배포됩니다.")
    else:  # pragma: no cover - 스키마가 막는다
        raise ValueError(itype)

    plan.add(tool, args, f"{itype}: {item['title']}", binds={f"{iid}.cmid": "cmid", f"{iid}.instance": "instance"})

    if tool in NO_SETTINGS_TOOLS:
        plan.add("update_activity", {"cmid": ref(f"{iid}.cmid"), "settings": settings}, f"ID number 기록: {iid}")
    if mode not in handled:
        plan.add(
            "set_completion",
            {"cmid": ref(f"{iid}.cmid"), "mode": mode, "posts": completion.get("posts"),
             "pass_grade": completion.get("pass_grade")},
            f"완료 조건 '{mode}': {iid}",
        )  # fmt: skip
    if itype == "quiz" and item.get("questions"):
        plan.add(
            "add_quiz_questions",
            {"quiz_id": ref(f"{iid}.instance"), "questions": [_question(q) for q in item["questions"]]},
            f"문항 {len(item['questions'])}개: {iid}",
        )
    if "rubric" in item and itype in ("assignment", "peer_review"):
        r = item["rubric"]
        plan.add(
            "set_rubric",
            {"cmid": ref(f"{iid}.cmid"), "name": r["name"], "description": r.get("description", ""),
             "criteria": r["criteria"], "area": "submissions"},
            f"루브릭: {iid}",
        )  # fmt: skip
        if itype == "peer_review" and any(lv["score"] != int(lv["score"]) for c in r["criteria"] for lv in c["levels"]):
            plan.note(iid, "warn", "워크숍 루브릭은 정수 점수만 받습니다.")


def file_source(spec: Spec, item: dict[str, Any]) -> str:
    """file 항목의 실제 원본: source 가 없으면 자료 매니페스트에서 찾는다."""
    if item.get("source"):
        return item["source"]
    return spec.materials[item["material"]]["source"]


def _file_source(plan: Plan, iid: str, source: str) -> dict[str, Any]:
    if source.startswith(("http://", "https://")):
        return {"file_url": source}
    plan.note(iid, "info", f"워크스페이스 파일 '{source}'은 실행기가 읽어 base64로 전달합니다.")
    return {"file_base64": {"$file": source}}


def _question(q: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"type": q["type"], "text": q["text"], "mark": q.get("mark", 1)}
    if q.get("name"):
        out["name"] = q["name"]
    if q.get("feedback"):
        out["generalfeedback"] = q["feedback"]
    t = q["type"]
    if t == "multichoice":
        choices = q.get("choices", [])
        n_correct = max(1, sum(bool(c.get("correct")) for c in choices))
        multiple = bool(q.get("multiple"))
        out["single"] = not multiple
        out["answers"] = [
            {"text": c["text"], "feedback": c.get("feedback", ""),
             "fraction": (round(1 / n_correct, 7) if multiple else 1.0) if c.get("correct") else 0.0}
            for c in choices
        ]  # fmt: skip
    elif t == "truefalse":
        out["correct"] = q["answer"]
    elif t == "shortanswer":
        out["answers"] = [{"text": a, "fraction": 1.0} for a in q["accepted_answers"]]
        out["usecase"] = q.get("case_sensitive", False)
    elif t == "essay":
        if q.get("grader_info"):
            out["graderinfo"] = q["grader_info"]
    return out
