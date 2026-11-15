import json
import shutil

import pytest

from coursespec.cli import main
from coursespec.patch import PatchError, apply_ops, patch_file
from coursespec.spec import load_spec
from coursespec.tutor import skill_md, tutor_pack

from .conftest import EXAMPLE


@pytest.fixture
def spec_copy(tmp_path):
    p = tmp_path / "c.yaml"
    shutil.copy(EXAMPLE, p)
    return p


def test_apply_ops_basic():
    doc = {"a": [1, 2], "b": {"c": 1}}
    out = apply_ops(doc, [{"op": "add", "path": "/a/-", "value": 3}, {"op": "replace", "path": "/b/c", "value": 2},
                          {"op": "remove", "path": "/a/0"}, {"op": "test", "path": "/b/c", "value": 2}])
    assert out == {"a": [2, 3], "b": {"c": 2}} and doc == {"a": [1, 2], "b": {"c": 1}}
    with pytest.raises(PatchError):
        apply_ops(doc, [{"op": "test", "path": "/b/c", "value": 9}])
    with pytest.raises(PatchError):
        apply_ops(doc, [{"op": "replace", "path": "/nope", "value": 1}])


def test_patch_preserves_comments_and_rejects_bad(spec_copy):
    before = spec_copy.read_text("utf-8")
    patch_file(spec_copy, [{"op": "replace", "path": "/units/0/title", "value": "1주차 — 새 제목"}])
    after = spec_copy.read_text("utf-8")
    assert "# 자료 매니페스트" in after and "1주차 — 새 제목" in after
    assert len(before.splitlines()) == len(after.splitlines())

    with pytest.raises(PatchError) as exc:  # 스키마 위반
        patch_file(spec_copy, [{"op": "replace", "path": "/units/0/items/0/type", "value": "lti"}])
    assert exc.value.errors
    with pytest.raises(PatchError):  # 린트 오류 (없는 학습목표)
        patch_file(spec_copy, [{"op": "add", "path": "/units/0/items/0/outcomes/-", "value": "lo9"}])
    assert "1주차 — 새 제목" in spec_copy.read_text("utf-8")  # 실패한 패치는 기록되지 않음


def test_patch_cli_dry_run(spec_copy, tmp_path, capsys):
    ops = tmp_path / "p.json"
    ops.write_text(json.dumps([{"op": "replace", "path": "/title", "value": "바뀐 과정"}]), "utf-8")
    assert main(["patch", str(spec_copy), str(ops), "--dry-run"]) == 0
    assert "바뀐 과정" not in spec_copy.read_text("utf-8")
    assert main(["patch", str(spec_copy), str(ops)]) == 0
    assert load_spec(spec_copy).title == "바뀐 과정"


def test_tutor_pack():
    from datetime import date

    spec = load_spec(EXAMPLE)
    pack = tutor_pack(spec, date(2027, 3, 2))
    assert [m["id"] for m in pack["materials"]] == ["m-autonomy", "m-scenarios", "m-ethics"]
    rules = {r["item"]: r for r in pack["integrity"]}
    assert rules["w1-quiz"]["until"] == "2027-03-08T23:59:00+09:00"
    assert rules["w2-scenario"]["from_day"] == 8 and rules["w2-scenario"]["until_day"] == 17
    assert rules["w3-peer"]["until_day"] == 21
    assert rules["w1-forum"]["mode"] == "no_ghostwriting"
    assert "w1-reading" not in rules
    assert pack["mapping"]["question_outcomes"]["cs:ai-agent-education:w1-quiz#q2"] == ["lo1"]
    md = skill_md(spec, pack)
    assert md.startswith("---\nname: tutor-ai-agent-education")
    assert "과제 1 — 내 수업 에이전트 시나리오" in md


def test_tutor_pack_cli(tmp_path, capsys):
    assert main(["tutor-pack", str(EXAMPLE), "--out", str(tmp_path)]) == 0
    assert (tmp_path / "SKILL.md").exists() and json.loads((tmp_path / "tutor-pack.json").read_text("utf-8"))
