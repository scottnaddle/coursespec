import json
from pathlib import Path

from coursespec.canvas_verify import parse_verify_steps, verify_canvas
from coursespec.cli import main
from coursespec.spec import load_spec

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "examples" / "design-agent-demo" / "course.coursespec.yaml"
FIXTURES = Path(__file__).parent / "fixtures"
SNAPSHOT = FIXTURES / "canvas-imscc-snapshot.json"
VERIFY_STEPS = FIXTURES / "canvas-verify-steps.json"

W1 = "1주차 — AI 윤리의 핵심 쟁점"
W2 = "2주차 — 사례 분석과 실천 원칙"
READING = "읽기 — 편향, 개인정보, 책임"
CASE = "사례 — 채용 AI와 개인정보"
DISCUSSION = "토론 — 생활 속 AI 윤리 사례"
ASSIGNMENT = "과제 — 나의 AI 활용 원칙과 실천 계획"
QUIZ = "1주차 확인 퀴즈"


def snapshot():
    return json.loads(SNAPSHOT.read_text("utf-8"))


def by_kind(result):
    return {c.kind: c for c in result.comparisons}


def test_demo_imscc_snapshot_reports_known_differences():
    result = verify_canvas(load_spec(DEMO), snapshot())
    comparisons = by_kind(result)

    modules = comparisons["modules"]
    assert modules.status == "일치"
    assert modules.expected == [W1, W2]
    assert modules.overall == "누락"
    item_status = {c.kind: c.status for c in modules.items}
    assert item_status[f"module_items:{W1}"] == "누락"
    assert item_status[f"module_items:{W2}"] == "일치"

    pages = comparisons["pages"]
    assert pages.status == "차이"
    assert pages.missing == []
    assert {r.title for r in pages.results} == {READING, CASE}
    assert all(r.status == "차이" for r in pages.results)
    assert all(r.note == "CC webcontent가 Canvas에서 File로 가져와졌다 (Page가 아님)" for r in pages.results)
    assert pages.note == "CC webcontent가 Canvas에서 File로 가져와졌다 (Page가 아님)"

    quizzes = comparisons["quizzes"]
    assert quizzes.status == "누락"
    assert quizzes.missing == [QUIZ]
    assert quizzes.note == "CC QTI 퀴즈가 Canvas 모듈·퀴즈·과제 목록에 없습니다"

    discussions = comparisons["discussions"]
    assert discussions.status == "차이"
    assert discussions.note == "CC 토론 리소스에 점수가 없어 무채점 토론으로 가져와졌다"
    discussion = discussions.results[0]
    assert discussion.title == DISCUSSION
    assert discussion.expected["points"] == 10
    assert discussion.actual["points_possible"] is None
    assert discussion.note == "CC 토론 리소스에 점수가 없어 무채점 토론으로 가져와졌다"

    assignments = comparisons["assignments"]
    assert assignments.status == "일치"
    assignment = assignments.results[0]
    assert assignment.title == ASSIGNMENT
    assert assignment.status == "일치"
    assert assignment.actual["points_possible"] == 100.0
    assert "online_text_entry" in assignment.actual["type"]

    assert not result.ok
    assert any(c.where == "grading" for c in result.conversions)
    assert any(c.where == "course" for c in result.conversions)


def test_snapshot_with_pages_and_quizzes_matches():
    data = snapshot()
    data["pages"] = [{"title": READING}, {"title": CASE}]
    data["quizzes"] = [{"title": QUIZ}]
    data["modules"][0]["items"].append({"title": QUIZ, "type": "Quiz"})
    data["discussions"][0]["points_possible"] = 10

    result = verify_canvas(load_spec(DEMO), data)
    comparisons = by_kind(result)

    assert comparisons["pages"].status == "일치"
    assert comparisons["quizzes"].status == "일치"
    assert comparisons["modules"].overall == "일치"
    assert result.ok


def test_cli_verify_lms_exit_and_json(capsys):
    code = main(["verify-lms", str(DEMO), "--target", "canvas", "--snapshot", str(SNAPSHOT), "--json"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert "comparison" in payload
    assert any(c["kind"] == "quizzes" and c["status"] == "누락" for c in payload["comparison"])


def test_verify_steps_pass_fail_and_absolute_url_rejected():
    steps = json.loads(VERIFY_STEPS.read_text("utf-8"))
    result = verify_canvas(load_spec(DEMO), snapshot(), verify_steps=steps)
    assert [s.result for s in result.steps] == ["통과", "실패"]
    assert result.steps[0].status == 201
    assert result.steps[1].status == 404
    assert result.steps[1].note == "non_json"

    rejected = parse_verify_steps(
        [
            {
                "about": "absolute",
                "method": "GET",
                "path_template": "https://canvas.invalid/api/v1/courses",
                "status": 200,
            }
        ]
    )
    assert rejected[0].result == "오류"
    assert "절대 URL" in rejected[0].note
    assert not rejected[0].ok


def test_new_sources_have_no_credentials_or_real_hosts():
    bad = ["http" + "://", "local" + "host", "80" + "95", "Bear" + "er ", "access_" + "token"]
    files = [
        ROOT / "src" / "coursespec" / "canvas_verify.py",
        SNAPSHOT,
        VERIFY_STEPS,
        Path(__file__),
    ]
    for path in files:
        text = path.read_text("utf-8")
        for token in bad:
            assert token not in text, path
