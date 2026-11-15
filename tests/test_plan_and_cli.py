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
