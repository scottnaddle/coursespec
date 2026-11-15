import json

import pytest

from coursespec.cli import main
from coursespec.plan import Step, collect, resolve

from .conftest import EXAMPLE


def test_resolve_keeps_types_and_inlines():
    bound = {"a.id": 7}
    assert resolve({"x": "${a.id}", "p": "/c/${a.id}/m", "l": ["${a.id}"]}, bound) == {"x": 7, "p": "/c/7/m", "l": [7]}
    with pytest.raises(KeyError):
        resolve("${missing}", bound)


def test_collect_dotted_path():
    bound = {}
    collect(Step("t", {}, "", binds={"u.s": "sections.1.section"}), {"sections": [{"section": 3}, {"section": 4}]}, bound)
    assert bound == {"u.s": 4}


def test_cli_lint_and_plan(capsys):
    assert main(["lint", str(EXAMPLE)]) == 0
    assert main(["plan", str(EXAMPLE), "--target", "moodle", "--start", "2027-03-02", "--json"]) == 0
    out = capsys.readouterr().out
    plan = json.loads(out[out.index("{"):])
    assert plan["target"] == "moodle" and plan["summary"]["steps"] > 10


def test_cli_plan_canvas_needs_account(capsys):
    assert main(["plan", str(EXAMPLE), "--target", "canvas", "--start", "2027-03-02"]) == 2


def test_cli_plan_canvas_post_import_needs_course_id(capsys):
    assert main([
        "plan", str(EXAMPLE), "--target", "canvas", "--start", "2027-03-02", "--post-import",
    ]) == 2
    capsys.readouterr()


def test_cli_plan_canvas_classic_quiz_and_post_import(capsys):
    assert main([
        "plan", str(EXAMPLE), "--target", "canvas", "--start", "2027-03-02",
        "--course-id", "5", "--canvas-quiz", "classic", "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert any(step["tool"] == "canvas_request" and step.get("about", "").startswith("Classic 퀴즈") for step in payload["steps"])

    assert main([
        "plan", str(EXAMPLE), "--target", "canvas", "--start", "2027-03-02",
        "--course-id", "5", "--post-import", "--canvas-quiz", "classic", "--json",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    tools = [step["tool"] for step in payload["steps"]]
    assert "canvas_create_classic_quiz" in tools
    assert "canvas_promote_file_to_page" in tools
    assert not any(step.get("about") == "강좌 생성" for step in payload["steps"])
