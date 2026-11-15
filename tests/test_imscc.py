import zipfile
from pathlib import Path

from lxml import etree

from coursespec.cli import main
from coursespec.imscc_verify import ASSIGN_NS, QTI_NS, verify_imscc
from coursespec.publishers.imscc import export_imscc
from coursespec.spec import from_data, load_spec

from .conftest import EXAMPLE


def _names(path):
    with zipfile.ZipFile(path) as zf:
        return set(zf.namelist())


def _read(path, name):
    with zipfile.ZipFile(path) as zf:
        return zf.read(name)


def _rewrite(src, dst, *, replace=None, remove=None):
    with zipfile.ZipFile(src) as zf:
        items = {name: zf.read(name) for name in zf.namelist()}
    if remove and remove in items:
        del items[remove]
    if replace:
        name, old, new = replace
        items[name] = items[name].replace(old, new)
    with zipfile.ZipFile(dst, "w") as zf:
        for name, data in items.items():
            zf.writestr(name, data)


def _fieldentries(xml):
    root = etree.fromstring(xml)
    return [el.text for el in root.iter(f"{{{QTI_NS}}}fieldentry")]


def test_export_example_creates_portable_package(tmp_path):
    spec = load_spec(EXAMPLE)
    dest = tmp_path / "course.imscc"
    result = export_imscc(spec, dest)

    assert result.path == dest and dest.is_file()
    names = _names(dest)
    assert "imsmanifest.xml" in names
    assert not any(name.startswith("course/") for name in names)
    assert "web_resources/w1-reading.html" in names
    assert "files/w1-notes/autonomy-levels.md" in names

    manifest = _read(dest, "imsmanifest.xml")
    text = manifest.decode("utf-8")
    assert "IMS Common Cartridge" in text and "1.3.0" in text
    assert 'type="webcontent"' in text
    assert 'type="assignment_xmlv1p0"' in text
    assert 'type="imsqti_xmlv1p2/imscc_xmlv1p3/assessment"' in text
    assert 'type="imsdt_xmlv1p3"' in text

    root = etree.fromstring(manifest)
    ns = {"cc": "http://www.imsglobal.org/xsd/imsccv1p3/imscp_v1p1"}
    units = root.xpath("//cc:item[starts-with(@identifier, 'unit_')]", namespaces=ns)
    assert {u.get("identifier") for u in units} == {"unit_w1", "unit_w2", "unit_w3", "unit_w4"}

    verify = verify_imscc(dest)
    assert verify.errors == []


def test_losses_are_reported_for_unrepresentable_items(tmp_path):
    result = export_imscc(load_spec(EXAMPLE), tmp_path / "course.imscc")
    losses = {c.where for c in result.conversions if c.severity == "loss"}

    assert {"w4-reflection", "w4-lecture", "agent-designer"} <= losses
    assert any(
        c.where == "w3-peer" and c.severity in ("loss", "warn") for c in result.conversions
    )
    names = _names(tmp_path / "course.imscc")
    assert "assignments/w3-peer.xml" in names


def test_quiz_question_types_map_to_cc_profiles(tmp_path):
    dest = tmp_path / "course.imscc"
    export_imscc(load_spec(EXAMPLE), dest)
    profiles = _fieldentries(_read(dest, "assessments/w1-quiz.xml"))
    assert "cc.multiple_choice.v0p1" in profiles
    assert "cc.true_false.v0p1" in profiles
    assert "cc.essay.v0p1" in profiles

    data = {
        "coursespec": "0.2",
        "id": "quiz-types",
        "title": "문항 유형",
        "outcomes": [{"id": "lo1", "statement": "설명할 수 있다"}],
        "grading": {"categories": [{"id": "cat", "name": "퀴즈", "weight": 100}]},
        "units": [
            {
                "id": "u1",
                "title": "1주차",
                "items": [
                    {
                        "id": "q1",
                        "type": "quiz",
                        "title": "유형 확인",
                        "outcomes": ["lo1"],
                        "grading": {"max": 10, "category": "cat"},
                        "completion": {"mode": "pass", "pass_grade": 6},
                        "questions": [
                            {
                                "type": "multichoice",
                                "text": "복수 정답",
                                "multiple": True,
                                "choices": [
                                    {"text": "가", "correct": True},
                                    {"text": "나", "correct": True},
                                    {"text": "다"},
                                ],
                            },
                            {
                                "type": "shortanswer",
                                "text": "단답",
                                "accepted_answers": ["서울", "Seoul"],
                            },
                        ],
                    }
                ],
            }
        ],
    }
    mini = tmp_path / "types.imscc"
    export_imscc(from_data(data), mini)
    profiles = _fieldentries(_read(mini, "assessments/q1.xml"))
    assert "cc.multiple_response.v0p1" in profiles
    assert "cc.fib.v0p1" in profiles
    assert verify_imscc(mini).errors == []


def test_assignment_xml_has_instructor_text_and_points(tmp_path):
    dest = tmp_path / "course.imscc"
    export_imscc(load_spec(EXAMPLE), dest)
    root = etree.fromstring(_read(dest, "assignments/w2-scenario.xml"))

    instructor = root.find(f"{{{ASSIGN_NS}}}instructor_text")
    assert instructor is not None and instructor.get("texttype") == "text/plain"
    gradable = root.find(f"{{{ASSIGN_NS}}}gradable")
    assert gradable is not None and gradable.get("points_possible") == "100"
    formats = {el.get("type") for el in root.iter(f"{{{ASSIGN_NS}}}format")}
    assert {"html", "file"} <= formats


def test_cli_export_and_verify_example(tmp_path, monkeypatch, capsys):
    out = tmp_path / "cli.imscc"
    assert main(["export", str(EXAMPLE), "--format", "imscc", "--out", str(out)]) == 0
    assert out.is_file()
    assert main(["verify", str(out)]) == 0

    monkeypatch.chdir(tmp_path)
    assert main(["export", str(EXAMPLE), "--format", "imscc"]) == 0
    assert (tmp_path / "ai-agent-education.imscc").is_file()
    capsys.readouterr()


def test_verify_rejects_broken_packages(tmp_path):
    good = tmp_path / "course.imscc"
    export_imscc(load_spec(EXAMPLE), good)

    wrong_version = tmp_path / "wrong-version.imscc"
    _rewrite(good, wrong_version, replace=("imsmanifest.xml", b"1.3.0", b"9.9.9"))
    assert verify_imscc(wrong_version).errors

    missing_file = tmp_path / "missing-file.imscc"
    _rewrite(good, missing_file, remove="web_resources/w1-reading.html")
    assert verify_imscc(missing_file).errors
