import pytest

from coursespec.lint import lint
from coursespec.spec import SpecError, from_data, load_spec

from .conftest import EXAMPLE


def codes(spec):
    return {f.code for f in lint(spec)}


def test_example_is_valid_and_clean():
    spec = load_spec(EXAMPLE)
    assert spec.id == "ai-agent-education"
    assert len(spec.units) == 4
    assert lint(spec) == []


def test_schema_rejects_unknown_type(minimal):
    data = minimal()
    data["units"][0]["items"][0]["type"] = "lti"
    with pytest.raises(SpecError) as exc:
        from_data(data)
    assert exc.value.errors


def test_schema_requires_page_content(minimal):
    data = minimal()
    del data["units"][0]["items"][0]["content"]
    with pytest.raises(SpecError):
        from_data(data)


def test_duplicate_and_unknown_refs(minimal):
    data = minimal()
    data["units"][0]["items"][1]["id"] = "p1"
    data["units"][0]["items"][0]["outcomes"] = ["nope"]
    data["units"][0]["items"][0]["requires"] = ["ghost"]
    c = codes(from_data(data))
    assert {"E001", "E002", "E003"} <= c


def test_requires_cycle(minimal):
    data = minimal()
    data["units"][0]["items"][0]["requires"] = ["a1"]
    data["units"][0]["items"][1]["requires"] = ["p1"]
    assert "E004" in codes(from_data(data))


def test_completion_rules(minimal):
    data = minimal()
    data["units"][0]["items"][0]["completion"] = {"mode": "pass", "pass_grade": 5}
    data["units"][0]["items"][1]["completion"] = {"mode": "posts", "posts": 2}
    c = codes(from_data(data))
    assert {"E008", "E011"} <= c


def test_dates_out_of_order(minimal):
    data = minimal()
    data["units"][0]["items"][1].update(opens_day=10, due_day=5)
    assert "E007" in codes(from_data(data))


def test_question_and_rubric_checks(minimal):
    data = minimal()
    data["units"][0]["items"].append({
        "id": "q1", "type": "quiz", "title": "퀴즈", "outcomes": ["lo1"], "grading": {"max": 10},
        "questions": [{"type": "multichoice", "text": "?", "choices": [{"text": "a"}, {"text": "b"}]}],
    })
    data["units"][0]["items"][1]["rubric"] = {"name": "r", "criteria": [
        {"description": "c", "levels": [{"definition": "x", "score": 1}, {"definition": "y", "score": 1}]}]}
    c = codes(from_data(data))
    assert {"E009", "E010"} <= c


def test_alignment_and_workload_warnings(minimal):
    data = minimal(
        outcomes=[{"id": "lo1", "statement": "a"}, {"id": "lo2", "statement": "b"}, {"id": "lo3", "statement": "c"}],
        policies={"workload": {"max_minutes_per_unit": 30}},
    )
    data["units"][0]["items"][0]["outcomes"] = ["lo2"]  # lo2: 다루지만 평가하지 않음
    data["units"][0]["items"][0]["estimated_minutes"] = 60
    c = codes(from_data(data))
    assert {"W101", "W102", "W105"} <= c


def test_weights_warning(minimal):
    data = minimal(grading={"categories": [{"id": "x", "name": "X", "weight": 30}]})
    data["units"][0]["items"][1]["grading"]["category"] = "x"
    assert "W104" in codes(from_data(data))
