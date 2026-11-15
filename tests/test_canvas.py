from datetime import date

import pytest

from coursespec.plan import collect, resolve
from coursespec.publishers.canvas import plan_canvas
from coursespec.spec import from_data, load_spec

from .conftest import EXAMPLE, ROOT

START = date(2027, 3, 2)
DEMO = ROOT / "examples" / "design-agent-demo" / "course.coursespec.yaml"


def run(plan):
    bound, out = {}, []
    ids = iter(range(1, 10_000))
    for step in plan.steps:
        args = resolve(step.args, bound)
        out.append(args)
        collect(step, {"id": next(ids), "url": f"page-{len(out)}"}, bound)
    return out


def test_requires_account_for_new_course():
    with pytest.raises(ValueError):
        plan_canvas(load_spec(EXAMPLE), START)


def test_example_plan_resolves_and_reports_losses():
    plan = plan_canvas(load_spec(EXAMPLE), START, account_id=1)
    calls = run(plan)
    assert all("${" not in str(c) for c in calls)
    losses = {c.where for c in plan.conversions if c.severity == "loss"}
    assert {"w4-lecture", "w4-reflection", "agent-designer", "w3-peer"} <= losses
    paths = [c["path"] for c in calls if "path" in c]
    assert not any("w4-lecture" in p for p in paths)


def test_quiz_items(minimal):
    data = minimal()
    data["units"][0]["items"].append({
        "id": "q1", "type": "quiz", "title": "퀴즈", "outcomes": ["lo1"], "grading": {"max": 10},
        "quiz": {"attempts": 3, "grade_method": "last", "time_limit_minutes": 10},
        "completion": {"mode": "pass", "pass_grade": 6},
        "questions": [
            {"type": "multichoice", "text": "?", "choices": [{"text": "a"}, {"text": "b", "correct": True}]},
            {"type": "truefalse", "text": "?", "answer": True},
            {"type": "shortanswer", "text": "?", "accepted_answers": ["x"]},
        ],
    })
    plan = plan_canvas(from_data(data), START, course_id=5)
    quiz = next(s for s in plan.steps if "New Quiz" in s.about)
    settings = quiz.args["json"]["quiz"]["quiz_settings"]
    assert settings["session_time_limit_in_seconds"] == 600
    assert settings["multiple_attempts"]["score_to_keep"] == "latest"
    items = [s.args["json"]["item"]["entry"] for s in plan.steps if s.about.startswith("문항")]
    assert [e["interaction_type_slug"] for e in items] == ["choice", "true-false", "essay"]
    assert items[0]["scoring_data"] == {"value": "c2"}
    assert any(c.severity == "loss" and c.where == "q1" for c in plan.conversions)
    mi = next(s for s in plan.steps if s.about == "모듈 아이템: q1")
    assert mi.args["json"]["module_item"]["completion_requirement"] == {"type": "min_score", "min_score": 6}


def test_prerequisites_widen_to_modules(example_data):
    plan = plan_canvas(from_data(example_data), START, course_id=5)
    puts = {s.about: s.args["json"]["module"] for s in plan.steps if s.args.get("method") == "PUT" and "modules" in s.args["path"]}
    assert puts["모듈 선수조건: w2"] == {"prerequisite_module_ids": ["${w1.module}"]}
    assert puts["모듈 선수조건: w1"] == {"require_sequential_progress": True}


def test_weights_applied(example_data):
    plan = plan_canvas(from_data(example_data), START, course_id=5)
    groups = [s.args["json"] for s in plan.steps if s.args.get("path", "").endswith("/assignment_groups")]
    assert [g["group_weight"] for g in groups] == [20, 20, 60]
    assert any(s.args["json"] == {"course": {"apply_assignment_group_weights": True}} for s in plan.steps)


def test_default_quiz_api_is_new_and_flagged_for_verification():
    plan = plan_canvas(load_spec(EXAMPLE), START, course_id=5)
    quiz = next(s for s in plan.steps if s.about.startswith("New Quiz"))
    assert quiz.verify
    assert quiz.args["path"] == "/api/quiz/v1/courses/5/quizzes"
    assert not any(s.about.startswith("Classic 퀴즈") for s in plan.steps)


def test_classic_quiz_path_and_question_mapping(minimal):
    data = minimal()
    data["units"][0]["items"].append({
        "id": "q1", "type": "quiz", "title": "퀴즈", "outcomes": ["lo1"], "grading": {"max": 10},
        "quiz": {"attempts": 3, "grade_method": "last", "time_limit_minutes": 10},
        "completion": {"mode": "pass", "pass_grade": 6},
        "questions": [
            {"type": "multichoice", "text": "?", "choices": [{"text": "a"}, {"text": "b", "correct": True}]},
            {"type": "truefalse", "text": "?", "answer": True},
            {"type": "shortanswer", "text": "?", "accepted_answers": ["x", "y"]},
            {"type": "essay", "text": "?", "mark": 2},
        ],
    })
    plan = plan_canvas(from_data(data), START, course_id=5, quiz_api="classic")
    quiz = next(s for s in plan.steps if s.about.startswith("Classic 퀴즈"))
    assert quiz.args["path"] == "/api/v1/courses/5/quizzes"
    assert not quiz.verify
    body = quiz.args["json"]["quiz"]
    assert body["allowed_attempts"] == 3
    assert body["scoring_policy"] == "keep_latest"
    assert body["time_limit"] == 10

    questions = [s.args["json"]["question"] for s in plan.steps if s.about.startswith("Classic 문항")]
    assert [q["question_type"] for q in questions] == [
        "multiple_choice_question",
        "true_false_question",
        "short_answer_question",
        "essay_question",
    ]
    assert [a["answer_weight"] for a in questions[0]["answers"]] == [0, 100]
    assert [a["answer_weight"] for a in questions[1]["answers"]] == [100, 0]
    assert [a["answer_text"] for a in questions[2]["answers"]] == ["x", "y"]
    assert all(
        s.args["path"] == "/api/v1/courses/5/quizzes/${q1.id}/questions"
        for s in plan.steps if s.about.startswith("Classic 문항")
    )
    resave = next(s for s in plan.steps if s.about.startswith("Classic 퀴즈 재저장"))
    assert resave.args["method"] == "PUT"
    assert resave.args["path"] == "/api/v1/courses/5/quizzes/${q1.id}"
    assert resave.args["json"] == {"quiz": {"notify_of_update": False}}
    assert not resave.verify
    module_item = next(s for s in plan.steps if s.about == "모듈 아이템: q1")
    assert module_item.args["json"]["module_item"]["type"] == "Quiz"
    assert not any("New Quiz" in s.about for s in plan.steps)


def test_classic_multiple_answers_use_multiple_answers_question(minimal):
    data = minimal()
    data["units"][0]["items"].append({
        "id": "q1", "type": "quiz", "title": "퀴즈", "outcomes": ["lo1"], "grading": {"max": 10},
        "questions": [{
            "type": "multichoice", "text": "?", "multiple": True,
            "choices": [{"text": "a", "correct": True}, {"text": "b", "correct": True}, {"text": "c"}],
        }],
    })
    plan = plan_canvas(from_data(data), START, course_id=5, quiz_api="classic")
    question = next(s for s in plan.steps if s.about.startswith("Classic 문항")).args["json"]["question"]
    assert question["question_type"] == "multiple_answers_question"
    assert [a["answer_weight"] for a in question["answers"]] == [100, 100, 0]


def test_post_import_requires_course_id():
    with pytest.raises(ValueError):
        plan_canvas(load_spec(DEMO), START, post_import=True)


def test_post_import_sets_unit_unlock_at_from_opens_day():
    plan = plan_canvas(load_spec(DEMO), START, course_id=5, quiz_api="classic", post_import=True)
    losses = [
        c for c in plan.conversions
        if c.where == "w2" and c.severity == "loss" and ("opens_day" in c.message or "unlock_at" in c.message)
    ]
    assert losses == []
    module = next(
        s for s in plan.steps
        if s.tool == "canvas_patch_imported"
        and s.args.get("kind") == "module"
        and s.args.get("title") == "2주차 — 사례 분석과 실천 원칙"
    )
    assert module.args["unit_title"] == "2주차 — 사례 분석과 실천 원칙"
    assert module.args["fields"]["unlock_at"].startswith("2027-03-09T00:00")


def test_post_import_classic_quiz_resaves_after_questions():
    plan = plan_canvas(load_spec(DEMO), START, course_id=5, quiz_api="classic", post_import=True)
    resave = next(s for s in plan.steps if s.about.startswith("Classic 퀴즈 재저장"))
    assert resave.args["method"] == "PUT"
    assert resave.args["path"] == "/api/v1/courses/5/quizzes/${w1-quiz.id}"
    assert resave.args["json"] == {"quiz": {"notify_of_update": False}}
    assert not resave.verify


def test_post_import_plan_supplements_imported_course_without_recreating():
    plan = plan_canvas(load_spec(DEMO), START, course_id=5, quiz_api="classic", post_import=True)
    abouts = [s.about for s in plan.steps]
    tools = [s.tool for s in plan.steps]

    assert not any("강좌 생성" in about for about in abouts)
    assert not any(tool == "canvas_request" and "/modules" in str(step.args.get("path", ""))
                   for tool, step in zip(tools, plan.steps))
    assert not any(about.startswith("page:") or about.startswith("topic:") for about in abouts)

    groups = next(s for s in plan.steps if s.tool == "canvas_ensure_assignment_groups")
    assert groups.args["groups"] == [
        {"id": "participation", "name": "참여", "weight": 20},
        {"id": "assignments", "name": "과제", "weight": 80},
    ]
    assert groups.args["apply_weights"] is True

    discussion = next(s for s in plan.steps if s.tool == "canvas_patch_imported" and s.args.get("kind") == "discussion")
    assert discussion.args["fields"]["assignment"]["points_possible"] == 10
    assert discussion.args["completion"] == {"type": "must_contribute"}

    assignment = next(s for s in plan.steps if s.tool == "canvas_patch_imported" and s.args.get("kind") == "assignment")
    assert assignment.args["fields"]["due_at"].startswith("2027-03-15T23:59")
    assert assignment.args["fields"]["assignment_group_id"] == "${cat.assignments.group_id}"

    promotes = [s for s in plan.steps if s.tool == "canvas_promote_file_to_page"]
    assert [s.args["title"] for s in promotes] == ["읽기 — 편향, 개인정보, 책임", "사례 — 채용 AI와 개인정보"]
    assert all(s.args["body_from"] == "imported_file" for s in promotes)

    quiz = next(s for s in plan.steps if s.tool == "canvas_create_classic_quiz")
    assert quiz.args["unit_title"] == "1주차 — AI 윤리의 핵심 쟁점"
    assert quiz.args["due_at"].startswith("2027-03-08T23:59")
    assert quiz.args["allowed_attempts"] == 2
    assert [q["question_type"] for q in quiz.args["questions"]] == [
        "multiple_choice_question",
        "true_false_question",
    ]
    assert quiz.args["completion"] == {"type": "min_score", "min_score": 6}


def test_post_import_plan_resolves_group_references():
    plan = plan_canvas(load_spec(DEMO), START, course_id=5, quiz_api="classic", post_import=True)
    bound: dict = {}
    for step in plan.steps:
        args = resolve(step.args, bound)
        assert "${" not in str(args)
        if step.tool == "canvas_ensure_assignment_groups":
            collect(step, {"groups": [{"id": 11}, {"id": 12}]}, bound)
        else:
            collect(step, {"id": 99}, bound)
    assert bound["cat.participation.group_id"] == 11
    assert bound["cat.assignments.group_id"] == 12


def test_post_import_with_new_quiz_adds_verification_steps():
    plan = plan_canvas(load_spec(DEMO), START, course_id=5, quiz_api="new", post_import=True)
    new_quiz = next(s for s in plan.steps if s.about.startswith("New Quiz"))
    assert new_quiz.verify
    assert new_quiz.args["path"] == "/api/quiz/v1/courses/5/quizzes"
    assert any(s.tool == "canvas_add_module_item" for s in plan.steps)
    assert not any(s.tool == "canvas_create_classic_quiz" for s in plan.steps)
