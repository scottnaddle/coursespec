from pathlib import Path

import yaml

from coursespec.lint import lint
from coursespec.spec import load_spec

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "design-agent" / "SKILL.md"
DEMO = ROOT / "examples" / "design-agent-demo"
SYLLABUS = DEMO / "syllabus.md"
COURSE = DEMO / "course.coursespec.yaml"


def test_skill_has_frontmatter_and_required_workflow():
    text = SKILL.read_text("utf-8")
    assert text.startswith("---\n")
    _, front, body = text.split("---", 2)
    meta = yaml.safe_load(front)
    assert meta["name"] == "design-agent"
    assert meta["description"]

    assert "syllabus" in body
    assert "coursespec lint" in body
    assert "coursespec patch" in body
    assert "다시 쓰지 않습니다" in body
    assert "LMS" in body and "배포" in body


def test_demo_course_validates_and_lints_without_errors():
    assert SYLLABUS.is_file() and COURSE.is_file()
    spec = load_spec(COURSE)
    findings = lint(spec)
    assert [f for f in findings if f.is_error] == []


def test_demo_reflects_syllabus_title_and_outcomes():
    syllabus = SYLLABUS.read_text("utf-8")
    spec = load_spec(COURSE)

    assert "AI 윤리 입문" in syllabus
    assert spec.title == "AI 윤리 입문"
    statements = " ".join(outcome["statement"] for outcome in spec.outcomes)
    for keyword in ("편향", "개인정보", "책임", "실천 계획"):
        assert keyword in syllabus and keyword in statements
    assert len(spec.units) == 2
