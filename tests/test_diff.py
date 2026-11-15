import json
from datetime import date

from coursespec.cli import main
from coursespec.diff import diff_moodle
from coursespec.spec import from_data

START = date(2027, 3, 2)


def outline(*modules):
    return {"sections": [{"section": 0, "name": "공지", "modules": []},
                         {"section": 1, "name": "1단원", "modules": list(modules)}]}


def module(cmid, name, modname, section=1, idnumber=None, instance=None, visible=1):
    m = {"id": cmid, "name": name, "modname": modname, "section": section,
         "instance": instance if instance is not None else cmid + 1000, "visible": visible}
    if idnumber:
        m["idnumber"] = idnumber
    return m


def record(spec_id, items):
    bound = {"course.id": 11}
    out = {}
    for iid, (cmid, name, modname) in items.items():
        bound[f"{iid}.cmid"] = cmid
        out[iid] = {"cmid": cmid, "name": name, "modname": modname}
    return {"spec_id": spec_id, "spec_version": "0.2.0", "target": "moodle", "course_id": 11,
            "start": "2027-03-02", "bound": bound, "items": out}


def test_title_change_is_blocked_drift(minimal):
    spec = from_data(minimal())
    rec = record("mini", {"p1": (152, "읽기", "page")})
    out = outline(module(152, "교수자가 고친 이름", "page", idnumber="cs:mini:p1"))
    result = diff_moodle(spec, START, 11, out, record=rec)
    assert result.blocked
    assert result.drifts[0].field == "name" and result.drifts[0].blocked
    assert not any(
        s.tool == "update_activity" and s.args.get("cmid") == 152 for s in result.steps
    )

    accepted = diff_moodle(spec, START, 11, out, record=rec, accept_drift=True)
    assert not accepted.blocked
    update = next(
        s for s in accepted.steps if s.tool == "update_activity" and s.args.get("name") == "읽기"
    )
    assert update.args == {"cmid": 152, "name": "읽기"}


def test_removed_recorded_item_is_hidden_not_deleted(minimal):
    spec = from_data(minimal())
    rec = record("mini", {"gone": (999, "옛 활동", "page")})
    out = outline(module(999, "옛 활동", "page", section=2, idnumber="cs:mini:gone"))
    result = diff_moodle(spec, START, 11, out, record=rec)
    hide = next(s for s in result.steps if s.tool == "set_activity_visibility")
    assert hide.args == {"cmid": 999, "visible": False}
    assert all("delete" not in s.tool for s in result.steps)


def test_announcements_forum_is_info_not_hidden(minimal):
    spec = from_data(minimal())
    out = outline(module(1, "강좌공지", "forum", section=0))
    result = diff_moodle(spec, START, 11, out)
    assert not any(s.tool == "set_activity_visibility" for s in result.steps)
    assert any(c.severity == "info" and "공지" in c.message for c in result.conversions)


def test_gradebook_idnumber_matches_quiz(minimal):
    data = minimal()
    data["units"][0]["items"].append({
        "id": "q1", "type": "quiz", "title": "새 퀴즈", "outcomes": ["lo1"],
        "grading": {"max": 10},
    })
    spec = from_data(data)
    out = outline(module(300, "퀴즈", "quiz"))
    gb = {"usergrades": [{"gradeitems": [
        {"cmid": 300, "idnumber": "cs:mini:q1", "itemname": "퀴즈", "itemmodule": "quiz",
         "categoryid": 1, "grademax": 10},
    ]}]}
    result = diff_moodle(spec, START, 11, out, gradebook=gb)
    update = next(s for s in result.steps if s.tool == "update_activity" and s.args.get("name") == "새 퀴즈")
    assert update.args == {"cmid": 300, "name": "새 퀴즈"}
    assert result.record["items"]["q1"]["idnumber"] == "cs:mini:q1"


def test_unique_fallback_matches_and_ambiguous_does_not_guess(minimal):
    spec = from_data(minimal())
    out = outline(module(152, "읽기", "page"))
    result = diff_moodle(spec, START, 11, out)
    assert "p1" in result.record["items"]
    assert not any(s.about.endswith(": page: 읽기") for s in result.steps)

    duplicate = outline(module(153, "읽기", "page", instance=1),
                         module(154, "읽기", "page", instance=2))
    ambiguous = diff_moodle(spec, START, 11, duplicate)
    assert "p1" in ambiguous.unmatched
    assert not any(s.about.endswith(": page: 읽기") for s in ambiguous.steps)


def test_diff_has_no_create_course_or_delete(minimal, tmp_path):
    spec = from_data(minimal())
    out = outline(module(152, "다른 이름", "page", idnumber="cs:mini:p1"),
                  module(999, "옛 활동", "page", idnumber="cs:mini:gone"))
    rec = record("mini", {"p1": (152, "읽기", "page"), "gone": (999, "옛 활동", "page")})
    result = diff_moodle(spec, START, 11, out, record=rec, accept_drift=True)
    tools = [s.tool for s in result.steps]
    assert "create_course" not in tools
    assert all("delete" not in t for t in tools)

    spec_path = tmp_path / "course.yaml"
    spec_path.write_text("""
coursespec: "0.1"
id: mini
title: 미니 과정
outcomes: [{id: lo1, statement: 무언가를 할 수 있다}]
units:
  - id: u1
    title: 1단원
    items:
      - {id: p1, type: page, title: 읽기, content: 본문, outcomes: [lo1]}
""", "utf-8")
    outline_path = tmp_path / "outline.json"
    record_path = tmp_path / "record.json"
    outline_path.write_text(json.dumps(out), "utf-8")
    record_path.write_text(json.dumps(rec), "utf-8")
    argv = ["diff", str(spec_path), "--target", "moodle", "--course-id", "11",
            "--start", "2027-03-02", "--outline", str(outline_path), "--record", str(record_path), "--json"]
    assert main(argv) == 2
    assert main(argv + ["--accept-drift"]) == 0
