from datetime import date, datetime
from zoneinfo import ZoneInfo

from coursespec.plan import collect, resolve
from coursespec.publishers.moodle import plan_moodle
from coursespec.spec import from_data, load_spec

from .conftest import EXAMPLE

START = date(2027, 3, 2)


def run(plan):
    """가짜 실행기: 모든 참조가 앞 단계에서 풀리는지 확인한다."""
    bound = {}
    calls = []
    counter = iter(range(100, 10_000))
    for step in plan.steps:
        args = resolve(step.args, bound)
        calls.append((step.tool, args))
        result = {"courseid": 7, "cmid": next(counter), "instance": next(counter),
                  "sections": [{"section": 10 + i} for i in range(20)]}
        collect(step, result, bound)
    return calls


def test_example_plan_resolves_end_to_end():
    plan = plan_moodle(load_spec(EXAMPLE), START)
    calls = run(plan)
    tools = [t for t, _ in calls]
    assert tools[0] == "create_course"
    course = next(a for t, a in calls if t == "create_course")
    assert course["visible"] == 0 and course["enablecompletion"] == 1
    assert tools.count("update_section") == 4
    # 접근 제한·성적부·배지는 활동 생성 뒤에 온다
    last_create = max(i for i, t in enumerate(tools) if t.startswith("create_") and t not in ("create_badge",))
    assert tools.index("set_access_restriction") > last_create
    assert tools[-1] == "create_badge"
    assert all("${" not in str(a) for _, a in calls)
    assert any(
        c.where == "course" and c.severity == "info" and "공지 포럼" in c.message
        for c in plan.conversions
    )


def test_ids_are_embedded_for_redeploy():
    plan = plan_moodle(load_spec(EXAMPLE), START)
    embedded = [s.args["settings"]["cmidnumber"] for s in plan.steps if "settings" in s.args and "cmidnumber" in s.args["settings"]]
    spec = load_spec(EXAMPLE)
    assert sorted(embedded) == sorted(spec.external_id(i) for i in spec.items)


def test_dates_follow_timezone():
    plan = plan_moodle(load_spec(EXAMPLE), START)
    quiz = next(s for s in plan.steps if s.tool == "create_quiz")
    close = datetime.fromtimestamp(quiz.args["timeclose"], ZoneInfo("Asia/Seoul"))
    assert (close.date(), close.hour, close.minute) == (date(2027, 3, 8), 23, 59)
    assert quiz.args["timelimit"] == 15 * 60
    assert quiz.args["completion_pass_grade"] == 6


def test_question_mapping(minimal):
    data = minimal()
    data["units"][0]["items"].append({
        "id": "q1", "type": "quiz", "title": "퀴즈", "outcomes": ["lo1"], "grading": {"max": 10},
        "questions": [
            {"type": "multichoice", "text": "?", "multiple": True,
             "choices": [{"text": "a", "correct": True}, {"text": "b", "correct": True}, {"text": "c"}]},
            {"type": "shortanswer", "text": "?", "accepted_answers": ["x", "y"], "case_sensitive": True},
        ],
    })
    plan = plan_moodle(from_data(data), START)
    qs = next(s for s in plan.steps if s.tool == "add_quiz_questions").args["questions"]
    assert qs[0]["single"] is False
    assert [a["fraction"] for a in qs[0]["answers"]] == [0.5, 0.5, 0.0]
    assert qs[1]["answers"] == [{"text": "x", "fraction": 1.0}, {"text": "y", "fraction": 1.0}]
    assert qs[1]["usecase"] is True


def test_existing_course_uses_add_sections(minimal):
    plan = plan_moodle(from_data(minimal()), START, course_id=42)
    first = plan.steps[0]
    assert first.tool == "add_sections" and first.args["course_id"] == 42
    calls = run(plan)
    page = next(a for t, a in calls if t == "create_page")
    assert page["section"] == 10 and page["course_id"] == 42


def test_completion_fallback_and_workshop(example_data):
    plan = plan_moodle(from_data(example_data), START)
    comp = [s.args for s in plan.steps if s.tool == "set_completion"]
    assert {"cmid": "${w3-peer.cmid}", "mode": "grade"} in [{k: c[k] for k in ("cmid", "mode")} for c in comp]
    assert any(c.where == "w3-peer" and c.severity == "warn" for c in plan.conversions)


def test_new_course_completion_off_warns(minimal):
    plan = plan_moodle(from_data(minimal()), START, enablecompletion=0)
    course = next(s for s in plan.steps if s.tool == "create_course")
    assert course.args["enablecompletion"] == 0
    assert any(c.where == "course" and c.severity == "warn" and "완료" in c.message for c in plan.conversions)


def test_example_lecture_has_no_default_grade():
    plan = plan_moodle(load_spec(EXAMPLE), START)
    lecture = next(s for s in plan.steps if s.tool == "create_openmaic")
    assert lecture.args["grade"] == 0
    assert any(
        c.where == "w4-lecture" and c.severity == "warn" and "기본 점수" in c.message
        for c in plan.conversions
    )
