import json
import shutil
from datetime import date

import pytest

from coursespec.lint import lint
from coursespec.patch import patch_file
from coursespec.plan import collect, resolve
from coursespec.publishers.canvas import plan_canvas
from coursespec.publishers.moodle import plan_moodle
from coursespec.publishers.openmaic import plan_openmaic, requirement
from coursespec.spec import from_data, load_spec

from .conftest import EXAMPLE

START = date(2027, 3, 2)


def codes(data):
    return {f.code for f in lint(from_data(data))}


def lecture_item(**lecture):
    return {"id": "lec", "type": "interactive_lecture", "title": "강의", "outcomes": ["lo1"],
            "completion": {"mode": "view"}, "lecture": lecture}


MAT = {"id": "m1", "title": "자료", "source": "materials/a.pdf", "units": ["u1"], "outcomes": ["lo1"],
       "uses": ["generation", "tutor"], "rights": {"license": "own"}}


def test_material_reference_rules(minimal):
    data = minimal(materials=[{**MAT, "units": ["nope"], "uses": ["tutor"], "rights": {}}])
    data["units"][0]["items"] += [
        {"id": "f1", "type": "file", "title": "파일", "material": "m1"},
        {"id": "f2", "type": "file", "title": "파일2", "material": "ghost"},
        lecture_item(prompt="p", materials=["m1"]),
    ]
    assert {"E015", "E016", "E017", "W111", "W112"} <= codes(data)


def test_lecture_needs_prompt_or_classroom(minimal):
    data = minimal()
    data["units"][0]["items"].append(lecture_item())
    assert "E014" in codes(data)
    data["units"][0]["items"][-1]["lecture"] = {"classroom": {"id": "stg"}}
    c = codes(data)
    assert "E014" not in c and "W115" in c


def test_tutor_coverage_warning(minimal):
    data = minimal(outcomes=[{"id": "lo1", "statement": "a"}, {"id": "lo2", "statement": "b"}], materials=[MAT])
    data["units"][0]["items"][1]["outcomes"] = ["lo1", "lo2"]
    assert "W113" in codes(data)


def test_file_from_material_in_both_lms(minimal):
    data = minimal(materials=[{**MAT, "uses": ["learner"]}])
    data["units"][0]["items"].append({"id": "f1", "type": "file", "title": "파일", "material": "m1"})
    spec = from_data(data)
    m = next(s for s in plan_moodle(spec, START).steps if s.tool == "create_resource")
    assert m.args["filename"] == "a.pdf" and m.args["file_base64"] == {"$file": "materials/a.pdf"}
    c = next(s for s in plan_canvas(spec, START, course_id=1).steps if s.tool == "canvas_upload_file")
    assert c.args["source"] == "materials/a.pdf"


def test_requirement_carries_course_context():
    spec = load_spec(EXAMPLE)
    text = requirement(spec, spec.items["w4-lecture"])
    assert text.startswith("학생 데이터와 AI 에이전트")
    assert "4주차 — 윤리와 책임" in text and "개인정보 위험을 평가" in text and "평가 수준" in text


def test_openmaic_plan_dedupes_uploads_and_skips_generated(minimal):
    data = minimal(materials=[MAT])
    data["units"][0]["items"] += [
        {**lecture_item(prompt="a", materials=["m1"]), "id": "lec1"},
        {**lecture_item(prompt="b", materials=["m1"]), "id": "lec2"},
        {**lecture_item(classroom={"id": "done", "archive": "x.json"}), "id": "lec3"},
    ]
    plan = plan_openmaic(from_data(data))
    tools = [s.tool for s in plan.steps]
    assert tools.count("openmaic_upload_material") == 1
    assert tools.count("openmaic_request") == 4  # 생성 요청 + 스냅샷 × 2
    assert any(c.where == "lec3" and "건너뜁니다" in c.message for c in plan.conversions)
    regen = plan_openmaic(from_data(data), regenerate=True)
    assert [s.tool for s in regen.steps].count("coursespec_patch") == 3


def test_generate_then_publish_end_to_end(tmp_path):
    """OpenMAIC 생성 계획을 가짜 실행기로 돌려 설계서에 기록하고, Moodle·Canvas 계획이 그 수업을 쓰는지."""
    spec_path = tmp_path / "course.yaml"
    shutil.copy(EXAMPLE, spec_path)
    plan = plan_openmaic(load_spec(spec_path), server="ubion-maic")
    bound = {}
    for step in plan.steps:
        args = resolve(step.args, bound)
        if step.tool == "openmaic_upload_material":
            result = {"materialId": f"mat-{args['filename']}"}
        elif step.tool == "openmaic_request" and args["method"] == "POST":
            assert args["json"]["materialIds"] == ["mat-ai-ethics-guide.pdf", "mat-agent-scenarios.pdf"]
            result = {"jobId": "job-1"}
        elif step.tool == "openmaic_wait_job":
            assert args["job_id"] == "job-1"
            result = {"result": {"classroomId": "stg_42"}}
        elif step.tool == "coursespec_patch":
            patch_file(spec_path, args["ops"])
            result = {}
        else:
            result = {}
        collect(step, result, bound)

    spec = load_spec(spec_path)
    assert spec.items["w4-lecture"]["lecture"]["classroom"] == {
        "id": "stg_42", "archive": "lectures/w4-lecture.stage.json", "server": "ubion-maic"}
    assert "# 생성 후" in spec_path.read_text("utf-8")  # 주석 보존

    moodle = next(s for s in plan_moodle(spec, START).steps if s.tool == "create_openmaic")
    assert moodle.args["lecture_id"] == "stg_42" and "prompt" not in moodle.args

    patch_file(spec_path, [{"op": "add", "path": spec.pointer["w4-lecture"] + "/lecture/exports",
                            "value": {"html": "lectures/w4-lecture.html"}}])
    canvas = plan_canvas(load_spec(spec_path), START, course_id=5)
    up = next(s for s in canvas.steps if s.about.startswith("수업 내보내기"))
    assert up.args["source"] == "lectures/w4-lecture.html"
    assert not any(c.where == "w4-lecture" and c.severity == "loss" for c in canvas.conversions)
