"""Canvas 퍼블리셔: 설계서 → Canvas REST API 호출 계획 (초안).

Canvas 는 아직 공식 MCP 가 일반 출시되지 않았으므로 REST API v1 과 New Quizzes API 를 직접 대상으로 한다.
공식 MCP 가 나오면 이 모듈의 단계만 그 도구 호출로 바꾸면 된다 (설계서와 린트는 그대로).

단계의 tool 은 일반 REST 호출(canvas_request)·파일 업로드(canvas_upload_file)와,
가져온 IMSCC 강좌를 보완하는 전용 도구(canvas_ensure_assignment_groups·canvas_patch_imported·
canvas_promote_file_to_page·canvas_create_classic_quiz·canvas_add_module_item)다.
전용 도구의 네트워크 호출은 실행기가 처리한다.

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
CLASSIC_SCORE = {"highest": "keep_highest", "last": "keep_latest"}
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


def plan_canvas(
    spec: Spec,
    start: date,
    course_id: int | None = None,
    account_id: int | None = None,
    quiz_api: str = "new",
    post_import: bool = False,
) -> Plan:
    if quiz_api not in ("new", "classic"):
        raise ValueError("quiz_api 는 'new' 또는 'classic' 이어야 합니다.")
    if post_import and course_id is None:
        raise ValueError("--post-import 는 기존 강좌에만 쓸 수 있습니다 (--course-id 필요).")

    tl = Timeline(start, spec.timezone)
    plan = Plan("canvas", spec.id, spec.data.get("version"), start.isoformat())
    req = lambda method, path, body, about, **kw: plan.add(  # noqa: E731
        "canvas_request", {"method": method, "path": path, "json": body}, about, **kw
    )

    if post_import:
        _plan_post_import(plan, spec, tl, course_id, quiz_api)
        return plan

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
        if _plan_item(plan, spec, tl, course, unit, item, quiz_api):
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


def _plan_item(
    plan: Plan,
    spec: Spec,
    tl: Timeline,
    course: Any,
    unit: dict[str, Any],
    item: dict[str, Any],
    quiz_api: str,
) -> bool:
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
    dates = _dates(tl, item)
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
        _plan_quiz(plan, course, item, group, dates, quiz_api)
        module_item.update(type="Quiz" if quiz_api == "classic" else "Assignment", content_id=ref(f"{iid}.id"))
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

    cr = _completion_requirement(plan, iid, item)
    if cr is not None:
        module_item["completion_requirement"] = cr
    req("POST", api(course, f"/modules/{ref(unit['id'] + '.module')}/items"), {"module_item": module_item},
        f"모듈 아이템: {iid}", binds={f"{iid}.module_item": "id"})  # fmt: skip
    return True


def _dates(tl: Timeline, item: dict[str, Any]) -> dict[str, Any]:
    return {
        "unlock_at": tl.iso(item.get("opens_day")),
        "due_at": tl.iso(item.get("due_day"), True),
        "lock_at": tl.iso(item.get("cutoff_day"), True),
    }


def _completion_requirement(plan: Plan, iid: str, item: dict[str, Any]) -> dict[str, Any] | None:
    completion = item.get("completion", {"mode": "none"})
    mode = completion["mode"]
    if mode not in COMPLETION:
        return None
    cr: dict[str, Any] = {"type": COMPLETION[mode]}
    if mode == "pass":
        cr["min_score"] = completion.get("pass_grade", 0)
    if mode == "grade":
        plan.note(iid, "warn", "Canvas 에는 '성적을 받으면 완료'가 없어 '제출하면 완료'로 바꿉니다.")
    if mode == "posts" and completion.get("posts", 1) > 1:
        plan.note(iid, "warn", f"Canvas 는 게시글 수({completion['posts']}개) 조건이 없어 '참여하면 완료'로 바꿉니다.")
    return cr


def _plan_quiz(
    plan: Plan,
    course: Any,
    item: dict[str, Any],
    group: Any,
    dates: dict[str, Any],
    quiz_api: str,
) -> None:
    if quiz_api == "classic":
        _plan_classic_quiz(plan, course, item, group, dates)
        return
    iid = item["id"]
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
    body = {"title": item["title"], "instructions": to_html(item.get("intro")), "points_possible": item.get("grading", {}).get("max", 10),
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


def _plan_classic_quiz(
    plan: Plan,
    course: Any,
    item: dict[str, Any],
    group: Any,
    dates: dict[str, Any],
) -> None:
    iid = item["id"]
    q = item.get("quiz", {})
    grading = item.get("grading", {})
    body: dict[str, Any] = {
        "title": item["title"],
        "description": to_html(item.get("intro")),
        "quiz_type": "assignment",
        "points_possible": grading.get("max", 10),
        "published": False,
        **dates,
        **_classic_settings(plan, iid, q),
    }
    if group is not None:
        body["assignment_group_id"] = group
    body = {k: v for k, v in body.items() if v is not None}
    plan.add("canvas_request",
             {"method": "POST", "path": api(course, "/quizzes"), "json": {"quiz": body}},
             f"Classic 퀴즈: {item['title']}", binds={f"{iid}.id": "id"})  # fmt: skip
    for pos, question in enumerate(item.get("questions", []), 1):
        plan.add("canvas_request",
                 {"method": "POST", "path": api(course, f"/quizzes/{ref(iid + '.id')}/questions"),
                  "json": {"question": _classic_question(plan, iid, pos, question)}},
                 f"Classic 문항 {pos}: {iid}")  # fmt: skip


def _classic_settings(plan: Plan, iid: str, q: dict[str, Any]) -> dict[str, Any]:
    settings: dict[str, Any] = {}
    if "time_limit_minutes" in q:
        settings["time_limit"] = q["time_limit_minutes"]
    attempts = q.get("attempts", 0)
    settings["allowed_attempts"] = attempts if attempts > 0 else -1
    method = q.get("grade_method", "highest")
    if method in CLASSIC_SCORE:
        settings["scoring_policy"] = CLASSIC_SCORE[method]
    else:
        settings["scoring_policy"] = "keep_highest"
        plan.note(iid, "warn", "Canvas Classic 퀴즈는 평균·첫 시도 채점을 지원하지 않아 최고 점수를 유지합니다.")
    return settings


def _classic_question(plan: Plan, iid: str, pos: int, q: dict[str, Any]) -> dict[str, Any]:
    t = q["type"]
    question: dict[str, Any] = {
        "question_name": q.get("name") or f"문항 {pos}",
        "question_text": to_html(q["text"]),
        "points_possible": q.get("mark", 1),
    }
    answers: list[dict[str, Any]] = []
    if t == "multichoice":
        correct = [c for c in q.get("choices", []) if c.get("correct")]
        question["question_type"] = "multiple_answers_question" if q.get("multiple") else "multiple_choice_question"
        if q.get("multiple") and len(correct) > 1:
            plan.note(iid, "info", f"문항 {pos}: 복수 정답은 multiple_answers_question 으로 만듭니다.")
        elif not q.get("multiple") and len(correct) > 1:
            plan.note(iid, "warn", f"문항 {pos}: 정답이 여러 개지만 단일 선택 문항이라 첫 정답만 반영됩니다.")
        first_correct = correct[0] if correct else None
        for choice in q.get("choices", []):
            is_correct = choice is first_correct or (q.get("multiple") and choice.get("correct"))
            answer = {"answer_text": choice["text"], "answer_weight": 100 if is_correct else 0}
            if choice.get("feedback"):
                answer["answer_comments"] = choice["feedback"]
            answers.append(answer)
    elif t == "truefalse":
        question["question_type"] = "true_false_question"
        correct = bool(q.get("answer"))
        answers = [
            {"answer_text": "참", "answer_weight": 100 if correct else 0},
            {"answer_text": "거짓", "answer_weight": 0 if correct else 100},
        ]
    elif t == "shortanswer":
        question["question_type"] = "short_answer_question"
        answers = [{"answer_text": a, "answer_weight": 100} for a in q.get("accepted_answers", []) if a]
        if q.get("case_sensitive"):
            plan.note(iid, "warn", f"문항 {pos}: Canvas Classic 단답형은 대소문자 구분 설정이 없습니다.")
    else:
        question["question_type"] = "essay_question"
        if q.get("grader_info"):
            question["comments"] = q["grader_info"]
    if answers:
        question["answers"] = answers
    if q.get("feedback"):
        question["correct_comments"] = q["feedback"]
    return question


def _plan_post_import(
    plan: Plan,
    spec: Spec,
    tl: Timeline,
    course: int,
    quiz_api: str,
) -> None:
    """이미 IMSCC를 가져온 강좌를 제목으로 찾아, 표준 CC가 담지 못한 설정만 REST로 보완한다."""
    plan.note(
        "course",
        "info",
        "가져온 IMSCC 강좌를 제목으로 찾아 점수·날짜·성적 가중치·완료 조건과 File로 들어온 페이지를 보완합니다. 강좌·모듈·활동은 다시 만들지 않습니다.",
    )
    _ensure_assignment_groups(plan, spec, course)
    for unit in spec.units:
        if unit.get("opens_day"):
            plan.note(
                unit["id"],
                "loss",
                f"post-import는 아직 단원 '{unit['title']}'의 opens_day를 Canvas 모듈 unlock_at으로 설정하지 않습니다. 가져온 뒤 Canvas에서 직접 공개일을 지정하세요.",
            )
    for _, unit, item in spec.iter_items():
        _plan_post_import_item(plan, tl, course, unit, item, quiz_api)


def _ensure_assignment_groups(plan: Plan, spec: Spec, course: int) -> None:
    if not spec.categories:
        return
    groups = [
        {"id": cat["id"], "name": cat["name"], "weight": cat.get("weight", 0)}
        for cat in spec.categories
    ]
    agg = spec.data.get("grading", {}).get("aggregation", "weighted_mean")
    binds = {f"cat.{group['id']}.group_id": f"groups.{pos}.id" for pos, group in enumerate(groups)}
    plan.add(
        "canvas_ensure_assignment_groups",
        {"course_id": course, "groups": groups, "apply_weights": agg != "mean"},
        "성적 그룹 보장",
        binds=binds,
    )
    if agg == "mean":
        plan.note("grading", "warn", "Canvas 에는 카테고리 단순 평균 집계가 없어 가중치 없이 점수 합산으로 계산됩니다.")


def _plan_post_import_item(
    plan: Plan,
    tl: Timeline,
    course: int,
    unit: dict[str, Any],
    item: dict[str, Any],
    quiz_api: str,
) -> None:
    iid, itype = item["id"], item["type"]
    title = item["title"]
    unit_title = unit["title"]
    exports = item.get("lecture", {}).get("exports", {})
    if itype == "interactive_lecture":
        if exports.get("html") or exports.get("video"):
            plan.note(iid, "warn", "가져온 강좌의 수업 파일을 그대로 씁니다. AI 교사·급우와의 상호작용과 AI 채점은 손실됩니다.")
        else:
            plan.note(iid, "loss", "인터랙티브 강의의 HTML·동영상 내보내기(lecture.exports)가 없어 보완할 파일이 없습니다.")
        return
    if itype in SKIPPED:
        plan.note(iid, "loss", SKIPPED[itype])
        return

    grading = item.get("grading", {})
    group = ref(f"cat.{grading['category']}.group_id") if grading.get("category") else None
    dates = _dates(tl, item)
    completion = _completion_requirement(plan, iid, item)

    if itype in ("page", "wiki"):
        plan.add(
            "canvas_promote_file_to_page",
            {"course_id": course, "title": title, "unit_title": unit_title, "body_from": "imported_file"},
            f"File→Page: {iid}",
        )
        if itype == "wiki":
            plan.note(iid, "warn", "위키는 Page로 보완하지만 학생 편집 역할은 자동으로 설정되지 않습니다. 가져온 뒤 확인하세요.")
        if completion is not None:
            _patch_module_item(plan, course, unit_title, title, iid, completion)
        return

    if itype == "file":
        if completion is not None:
            _patch_module_item(plan, course, unit_title, title, iid, completion)
        return

    if itype in ("assignment", "peer_review"):
        fields = _compact({"points_possible": grading.get("max"), "assignment_group_id": group, **dates})
        if itype == "peer_review":
            pr = item.get("peer_review", {})
            if pr.get("assessment_max"):
                plan.note(iid, "loss", "Canvas 동료 검토는 평가 활동 자체에 점수를 주지 않습니다 (Moodle 워크숍의 평가 점수 손실).")
            if pr.get("assessment_due_day"):
                plan.note(iid, "warn", "동료 평가 마감일은 Canvas 에서 별도로 지정할 수 없어 과제 마감 기준으로 운영됩니다.")
        if "rubric" in item:
            plan.note(iid, "warn", "루브릭은 post-import에서 자동으로 연결하지 않습니다. 가져온 과제에 Canvas에서 다시 연결하세요.")
        _patch_content(plan, course, "assignment", title, unit_title, fields, completion, f"과제 보완: {iid}")
        return

    if itype in ("discussion", "glossary"):
        if itype == "glossary":
            plan.note(iid, "loss", "용어집은 CC에서 파일로 가져와져 post-import에서 토론으로 자동 변환할 수 없습니다.")
            return
        fields: dict[str, Any] = {}
        if grading:
            fields["assignment"] = _compact(
                {"points_possible": grading.get("max"), "assignment_group_id": group, **dates}
            )
        elif any(dates.values()):
            plan.note(iid, "warn", "채점하지 않는 토론은 Canvas에서 날짜를 지정할 수 없습니다.")
        _patch_content(plan, course, "discussion", title, unit_title, fields, completion, f"토론 보완: {iid}")
        return

    if itype == "quiz":
        _plan_post_import_quiz(plan, course, unit_title, item, group, dates, completion, quiz_api)
        return

    raise ValueError(itype)  # pragma: no cover - 스키마·SKIPPED 가 막는다


def _compact(values: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in values.items() if v is not None}


def _patch_content(
    plan: Plan,
    course: int,
    kind: str,
    title: str,
    unit_title: str,
    fields: dict[str, Any],
    completion: dict[str, Any] | None,
    about: str,
) -> None:
    args: dict[str, Any] = {
        "course_id": course,
        "kind": kind,
        "title": title,
        "unit_title": unit_title,
        "fields": fields,
    }
    if completion is not None:
        args["completion"] = completion
    plan.add("canvas_patch_imported", args, about)


def _patch_module_item(
    plan: Plan,
    course: int,
    unit_title: str,
    title: str,
    iid: str,
    completion: dict[str, Any],
) -> None:
    plan.add(
        "canvas_patch_imported",
        {"course_id": course, "kind": "module_item", "title": title, "unit_title": unit_title, "completion": completion},
        f"완료 조건: {iid}",
    )


def _plan_post_import_quiz(
    plan: Plan,
    course: int,
    unit_title: str,
    item: dict[str, Any],
    group: Any,
    dates: dict[str, Any],
    completion: dict[str, Any] | None,
    quiz_api: str,
) -> None:
    iid = item["id"]
    title = item["title"]
    q = item.get("quiz", {})
    if quiz_api == "classic":
        args = _compact(
            {
                "course_id": course,
                "unit_title": unit_title,
                "title": title,
                "description": to_html(item.get("intro")),
                "quiz_type": "assignment",
                "points_possible": item.get("grading", {}).get("max", 10),
                "assignment_group_id": group,
                **dates,
                **_classic_settings(plan, iid, q),
                "questions": [
                    _classic_question(plan, iid, pos, question)
                    for pos, question in enumerate(item.get("questions", []), 1)
                ],
                "completion": completion,
            }
        )
        plan.add(
            "canvas_create_classic_quiz",
            args,
            f"Classic 퀴즈 생성: {title}",
            binds={f"{iid}.id": "id"},
        )
        return

    _plan_quiz(plan, course, item, group, dates, "new")
    args = _compact(
        {
            "course_id": course,
            "unit_title": unit_title,
            "title": title,
            "type": "Assignment",
            "content_id": ref(f"{iid}.id"),
            "completion": completion,
        }
    )
    plan.add("canvas_add_module_item", args, f"모듈 아이템 추가: {iid}")
    plan.note(
        iid,
        "warn",
        "New Quizzes API는 호스팅 Canvas에서만 형식 검증이 가능합니다. 오픈소스/테스트 인스턴스에는 API가 없을 수 있으니 --canvas-quiz classic을 쓰세요.",
    )


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
