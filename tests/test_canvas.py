from datetime import date

import pytest

from coursespec.plan import collect, resolve
from coursespec.publishers.canvas import plan_canvas
from coursespec.spec import from_data, load_spec

from .conftest import EXAMPLE

START = date(2027, 3, 2)


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
