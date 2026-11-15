"""설계 린트: 스키마로는 잡을 수 없는 의미 오류와 설계 품질 점검.

E = 배포를 막는 오류, W = 설계 검토가 필요한 경고.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .spec import Spec

GRADED_COMPLETION = {"grade", "pass"}
SUBMIT_TYPES = {"assignment", "peer_review", "survey"}
POST_TYPES = {"discussion"}
# 이 길이를 넘으면 Moodle ID number(100자)에 들어가지 않는다.
MAX_EXTERNAL_ID = 100


@dataclass(frozen=True)
class Finding:
    code: str
    where: str
    message: str

    @property
    def is_error(self) -> bool:
        return self.code.startswith("E")

    def __str__(self) -> str:
        return f"{self.code} {self.where}: {self.message}"


def lint(spec: Spec) -> list[Finding]:
    out: list[Finding] = []
    add = lambda code, where, msg: out.append(Finding(code, where, msg))  # noqa: E731

    outcome_ids = {o["id"] for o in spec.outcomes}
    category_ids = {c["id"] for c in spec.categories}

    # E001 중복 id (단원·활동·학습목표·카테고리·배지는 같은 이름공간)
    all_ids = (
        [u["id"] for u in spec.units]
        + [it["id"] for _, _, it in spec.iter_items()]
        + list(outcome_ids)
        + [c["id"] for c in spec.categories]
        + [b["id"] for b in spec.badges]
        + [m["id"] for m in spec.data.get("materials", [])]
    )
    for dup, n in Counter(all_ids).items():
        if n > 1:
            add("E001", dup, f"id가 {n}번 쓰였습니다. 설계서 안에서 유일해야 합니다.")

    for ui, unit in enumerate(spec.units):
        for ref in unit.get("requires", []):
            if ref not in spec.items:
                add("E003", unit["id"], f"requires 의 '{ref}' 활동이 없습니다.")
            elif spec.unit_index[spec.unit_of[ref]] >= ui:
                add("W106", unit["id"], f"단원이 같은 단원이나 뒤 단원의 활동 '{ref}'을 선수조건으로 가집니다.")

    for ui, unit, item in spec.iter_items():
        iid, itype = item["id"], item["type"]
        for ref in item.get("outcomes", []):
            if ref not in outcome_ids:
                add("E002", iid, f"학습목표 '{ref}'가 정의되지 않았습니다.")
        for q in item.get("questions", []):
            for ref in q.get("outcomes", []):
                if ref not in outcome_ids:
                    add("E002", iid, f"문항의 학습목표 '{ref}'가 정의되지 않았습니다.")
        for ref in item.get("requires", []):
            if ref not in spec.items:
                add("E003", iid, f"requires 의 '{ref}' 활동이 없습니다.")
            elif spec.unit_index[spec.unit_of[ref]] > ui:
                add("W106", iid, f"뒤 단원의 활동 '{ref}'을 선수조건으로 가집니다.")

        grading = item.get("grading")
        if grading and grading.get("category") and grading["category"] not in category_ids:
            add("E005", iid, f"성적 카테고리 '{grading['category']}'가 정의되지 않았습니다.")
        if grading and category_ids and not grading.get("category"):
            add("W109", iid, "성적 카테고리가 지정되지 않아 과정 총점 아래에 바로 놓입니다.")

        opens, due, cutoff = item.get("opens_day"), item.get("due_day"), item.get("cutoff_day")
        if opens and due and due < opens:
            add("E007", iid, f"마감일({due})이 공개일({opens})보다 이릅니다.")
        if due and cutoff and cutoff < due:
            add("E007", iid, f"최종 마감일({cutoff})이 마감일({due})보다 이릅니다.")
        unit_open = unit.get("opens_day")
        if unit_open and due and due < unit_open:
            add("E007", iid, f"마감일({due})이 단원 공개일({unit_open})보다 이릅니다.")

        completion = item.get("completion", {})
        mode = completion.get("mode")
        if mode in GRADED_COMPLETION and not grading and itype != "quiz":
            add("E008", iid, f"완료 조건 '{mode}'에는 grading 이 필요합니다.")
        if mode == "pass" and "pass_grade" not in completion:
            add("E008", iid, "완료 조건 'pass'에는 pass_grade 가 필요합니다.")
        if mode == "pass" and grading and completion.get("pass_grade", 0) > grading["max"]:
            add("E008", iid, "pass_grade 가 만점보다 큽니다.")
        if mode == "submit" and itype not in SUBMIT_TYPES:
            add("E011", iid, f"'{itype}' 유형에는 완료 조건 'submit'을 쓸 수 없습니다.")
        if mode == "posts" and itype not in POST_TYPES:
            add("E011", iid, f"'{itype}' 유형에는 완료 조건 'posts'를 쓸 수 없습니다.")

        if itype == "quiz":
            questions = item.get("questions", [])
            if not questions:
                add("W107", iid, "문항이 없는 퀴즈입니다.")
            for qi, q in enumerate(questions, 1):
                _check_question(q, f"{iid}#q{qi}", add)
        if "rubric" in item:
            _check_rubric(item["rubric"], iid, add)
            if itype not in ("assignment", "peer_review"):
                add("W110", iid, f"'{itype}' 유형의 루브릭은 배포되지 않습니다.")

        if len(spec.external_id(iid)) > MAX_EXTERNAL_ID:
            add("E012", iid, "설계서 id 와 활동 id 가 너무 길어 LMS ID number 에 들어가지 않습니다.")

    _lint_materials(spec, outcome_ids, add)

    # E004 선수조건 순환
    for cycle in _cycles(spec):
        add("E004", cycle[0], "선수조건이 순환합니다: " + " → ".join(cycle))

    # 배지
    for badge in spec.badges:
        for ref in badge["criteria"].get("items", []):
            if ref not in spec.items:
                add("E006", badge["id"], f"배지 조건의 '{ref}' 활동이 없습니다.")
            elif spec.items[ref].get("completion", {}).get("mode", "none") == "none":
                add("W108", badge["id"], f"'{ref}'에 완료 조건이 없어 배지가 수여되지 않습니다.")

    # 가중치 합
    agg = spec.data.get("grading", {}).get("aggregation", "weighted_mean")
    if spec.categories and agg != "mean":
        total = sum(c.get("weight", 0) for c in spec.categories)
        if abs(total - 100) > 1e-6:
            add("W104", "grading", f"카테고리 가중치 합이 {total:g}입니다 (100 권장).")
        for c in spec.categories:
            if "weight" not in c:
                add("E013", c["id"], f"집계 방식 '{agg}'에는 카테고리 weight 가 필요합니다.")

    # 구성적 정렬
    covered: set[str] = set()
    assessed: set[str] = set()
    for _, _, item in spec.iter_items():
        refs = set(item.get("outcomes", []))
        for q in item.get("questions", []):
            refs |= set(q.get("outcomes", []))
        covered |= refs
        if item.get("grading"):
            assessed |= refs
            if not refs and outcome_ids:
                add("W103", item["id"], "평가 활동이 어떤 학습목표와도 연결되어 있지 않습니다.")
    for o in spec.outcomes:
        if o["id"] not in covered:
            add("W102", o["id"], "이 학습목표를 다루는 활동이 없습니다.")
        elif o["id"] not in assessed:
            add("W101", o["id"], "이 학습목표를 평가하는 활동(grading 있음)이 없습니다.")

    # 학습 부담
    limit = spec.data.get("policies", {}).get("workload", {}).get("max_minutes_per_unit")
    if limit:
        for unit in spec.units:
            minutes = sum(i.get("estimated_minutes", 0) for i in unit.get("items", []))
            if minutes > limit:
                add("W105", unit["id"], f"예상 학습시간 {minutes}분이 단원 상한 {limit}분을 넘습니다.")

    order = {c: i for i, c in enumerate(["E001", "E002", "E003", "E004"])}
    return sorted(out, key=lambda f: (not f.is_error, order.get(f.code, 99), f.code, f.where))


def _lint_materials(spec: Spec, outcome_ids: set[str], add) -> None:
    unit_ids = {u["id"] for u in spec.units}
    for m in spec.materials.values():
        for ref in m.get("units", []):
            if ref not in unit_ids:
                add("E016", m["id"], f"단원 '{ref}'이 없습니다.")
        for ref in m.get("outcomes", []):
            if ref not in outcome_ids:
                add("E002", m["id"], f"학습목표 '{ref}'가 정의되지 않았습니다.")
        if m.get("uses") and not m.get("rights", {}).get("license"):
            add("W112", m["id"], "자료의 이용 권리(rights.license)가 확인되지 않았습니다.")

    for _, _, item in spec.iter_items():
        iid = item["id"]
        if "material" in item:
            m = spec.materials.get(item["material"])
            if m is None:
                add("E015", iid, f"자료 '{item['material']}'이 매니페스트에 없습니다.")
            elif "learner" not in m.get("uses", []):
                add("E017", iid, f"자료 '{m['id']}'은 학습자 배포(uses: learner)가 허용되지 않았습니다.")
        if item["type"] == "interactive_lecture":
            lec = item.get("lecture", {})
            if not lec.get("prompt") and not lec.get("classroom"):
                add("E014", iid, "인터랙티브 강의에는 lecture.prompt 나 생성된 lecture.classroom 이 필요합니다.")
            for ref in lec.get("materials", []):
                m = spec.materials.get(ref)
                if m is None:
                    add("E015", iid, f"자료 '{ref}'이 매니페스트에 없습니다.")
                elif "generation" not in m.get("uses", []):
                    add("W111", iid, f"자료 '{ref}'은 콘텐츠 생성용(uses: generation)으로 표시되지 않았습니다.")
            if lec.get("classroom") and not lec["classroom"].get("archive"):
                add("W115", iid, "생성된 수업의 내보내기(classroom.archive)가 없어 워크스페이스에서 버전 관리되지 않습니다.")

    tutor = [m for m in spec.materials.values() if "tutor" in m.get("uses", [])]
    if tutor:
        covered = {o for m in tutor for o in m.get("outcomes", [])}
        for o in spec.outcomes:
            if o["id"] not in covered:
                add("W113", o["id"], "이 학습목표를 다루는 튜터용 자료(uses: tutor)가 없습니다.")


def _check_question(q: dict[str, Any], where: str, add) -> None:
    t = q["type"]
    if t == "multichoice":
        choices = q.get("choices", [])
        correct = [c for c in choices if c.get("correct")]
        if len(choices) < 2:
            add("E009", where, "선다형 문항에는 보기가 2개 이상 필요합니다.")
        if not correct:
            add("E009", where, "선다형 문항에 정답 보기가 없습니다.")
        if len(correct) > 1 and not q.get("multiple"):
            add("E009", where, "정답이 여러 개이면 multiple: true 로 표시하세요.")
    elif t == "truefalse" and "answer" not in q:
        add("E009", where, "참/거짓 문항에 answer 가 없습니다.")
    elif t == "shortanswer" and not q.get("accepted_answers"):
        add("E009", where, "단답형 문항에 accepted_answers 가 없습니다.")


def _check_rubric(rubric: dict[str, Any], where: str, add) -> None:
    for ci, crit in enumerate(rubric["criteria"], 1):
        scores = [lv["score"] for lv in crit["levels"]]
        if len(set(scores)) != len(scores):
            add("E010", where, f"루브릭 기준 {ci}의 수준 점수가 겹칩니다.")


def _cycles(spec: Spec) -> list[list[str]]:
    graph = {iid: [r for r in it.get("requires", []) if r in spec.items] for iid, it in spec.items.items()}
    seen: set[str] = set()
    stack: list[str] = []
    on_stack: set[str] = set()
    found: list[list[str]] = []

    def visit(node: str) -> None:
        seen.add(node)
        stack.append(node)
        on_stack.add(node)
        for nxt in graph[node]:
            if nxt in on_stack:
                found.append(stack[stack.index(nxt):] + [nxt])
            elif nxt not in seen:
                visit(nxt)
        stack.pop()
        on_stack.discard(node)

    for node in graph:
        if node not in seen:
            visit(node)
    return found
