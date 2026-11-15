"""Canvas IMSCC 가져오기 결과를 설계서와 오프라인 비교한다.

네트워크를 호출하지 않는다. 실행기가 Canvas REST 로 이미 읽어 둔 스냅샷 JSON과
REST plan 의 `verify=True` 단계 실행 결과(HTTP 상태·about·path_template)를 입력으로 받아,
`.imscc` 가져오기가 설계서와 얼마나 맞는지 보고한다. 호스트·토큰은 입력에 넣지 않는다.
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .plan import Conversion
from .spec import Spec

MATCH = "일치"
MISSING = "누락"
DIFF = "차이"

PAGE_TYPES = {"page", "wiki"}
DISCUSSION_TYPES = {"discussion", "glossary"}
ASSIGNMENT_TYPES = {"assignment", "peer_review"}
QUIZ_TYPES = {"quiz"}
SUBMISSION = {"text": "online_text_entry", "file": "online_upload", "url": "online_url"}

PAGE_FILE_NOTE = "CC webcontent가 Canvas에서 File로 가져와졌다 (Page가 아님)"
DISCUSSION_POINTS_NOTE = "CC 토론 리소스에 점수가 없어 무채점 토론으로 가져와졌다"
QUIZ_MISSING_NOTE = "CC QTI 퀴즈가 Canvas 모듈·퀴즈·과제 목록에 없습니다"

URL_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
STATUS_MARK = {MATCH: "✓", MISSING: "✗", DIFF: "!"}


@dataclass
class ItemResult:
    """활동 하나의 비교 결과. expected/actual 은 작은 dict 또는 스냅샷 항목이다."""

    kind: str
    title: str
    status: str
    expected: Any = None
    actual: Any = None
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Comparison:
    """종류별 비교 결과. modules 는 items 에 모듈 아이템 비교를 중첩한다."""

    kind: str
    status: str
    expected: list[Any] = field(default_factory=list)
    actual: list[Any] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)
    note: str = ""
    results: list[ItemResult] = field(default_factory=list)
    items: list["Comparison"] = field(default_factory=list)
    overall: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kind": self.kind,
            "status": self.status,
            "expected_count": len(self.expected),
            "actual_count": len(self.actual),
            "expected": self.expected,
            "actual": self.actual,
            "missing": self.missing,
            "extra": self.extra,
        }
        if self.note:
            data["note"] = self.note
        if self.overall is not None:
            data["overall"] = self.overall
        if self.results:
            data["results"] = [r.to_dict() for r in self.results]
        if self.items:
            data["items"] = [c.to_dict() for c in self.items]
        return data


@dataclass
class StepReport:
    """REST plan 의 verify=True 단계 실행 결과. path_template 만 받는다."""

    about: str
    method: str
    path_template: str
    status: int | None
    result: str
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.result == "통과"

    def to_dict(self) -> dict[str, Any]:
        return {
            "about": self.about,
            "method": self.method,
            "path_template": self.path_template,
            "status": self.status,
            "result": self.result,
            "note": self.note,
        }


@dataclass
class CanvasVerifyResult:
    spec_id: str
    spec_version: str | None
    comparisons: list[Comparison] = field(default_factory=list)
    conversions: list[Conversion] = field(default_factory=list)
    steps: list[StepReport] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(_effective_status(c) == MATCH for c in self.comparisons) and all(s.ok for s in self.steps)

    def to_dict(self) -> dict[str, Any]:
        counts = {s: sum(_effective_status(c) == s for c in self.comparisons) for s in (MATCH, MISSING, DIFF)}
        step_counts = {s: sum(st.result == s for st in self.steps) for s in ("통과", "실패", "오류")}
        return {
            "target": "canvas",
            "spec": {"id": self.spec_id, "version": self.spec_version},
            "summary": {
                MATCH: counts[MATCH],
                MISSING: counts[MISSING],
                DIFF: counts[DIFF],
                "verify_steps": step_counts,
                "ok": self.ok,
            },
            "comparison": [c.to_dict() for c in self.comparisons],
            "conversions": [asdict(c) for c in self.conversions],
            "verify_steps": [s.to_dict() for s in self.steps],
        }

    def to_text(self) -> str:
        lines = [
            f"Canvas 가져오기 검증 → canvas  (설계서 {self.spec_id} {self.spec_version or ''})",
            "",
            "비교 결과",
        ]
        for c in self.comparisons:
            overall = f", overall {c.overall}" if c.overall else ""
            lines.append(f"  {c.kind}: {c.status}{overall}")
            for r in c.results:
                lines.append(_item_line(r, "    "))
            for child in c.items:
                lines.append(f"    · {child.kind}: {child.status}")
                for r in child.results:
                    lines.append(_item_line(r, "      "))
        if self.conversions:
            lines.extend(["", "변환 보고서"])
            mark = {"info": "  ·", "warn": "  !", "loss": "  ✗"}
            for c in self.conversions:
                lines.append(f"{mark[c.severity]} [{c.where}] {c.message}")
        if self.steps:
            lines.extend(["", "REST plan verify 단계"])
            for s in self.steps:
                mark = "✓" if s.ok else ("!" if s.result == "오류" else "✗")
                status = f" ({s.status})" if s.status is not None else ""
                note = f" — {s.note}" if s.note else ""
                lines.append(f"  {mark} {s.about}{status}{note}")
        counts = {s: sum(_effective_status(c) == s for c in self.comparisons) for s in (MATCH, MISSING, DIFF)}
        step_counts = {s: sum(st.result == s for st in self.steps) for s in ("통과", "실패", "오류")}
        verdict = "통과" if self.ok else "실패"
        lines.extend(
            [
                "",
                f"결과: 일치 {counts[MATCH]} · 누락 {counts[MISSING]} · 차이 {counts[DIFF]}"
                f" | verify 단계 통과 {step_counts['통과']} · 실패 {step_counts['실패']} · 오류 {step_counts['오류']}"
                f" | {verdict}",
            ]
        )
        return "\n".join(lines)


def _item_line(result: ItemResult, indent: str) -> str:
    mark = STATUS_MARK.get(result.status, "?")
    note = f" — {result.note}" if result.note else ""
    return f"{indent}{mark} {result.title}: {result.status}{note}"


def _effective_status(comparison: Comparison) -> str:
    return comparison.overall if comparison.kind == "modules" and comparison.overall else comparison.status


def _titles(rows: Any) -> list[str]:
    if not isinstance(rows, list):
        return []
    return [str(row.get("title", "")) for row in rows if isinstance(row, dict)]


def _find(rows: Any, title: str) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and str(row.get("title", "")) == title:
            return row
    return None


def _type_text(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return "" if value is None else str(value)


def _type_set(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(v) for v in value}
    if value is None:
        return set()
    return {str(value)}


def _points(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _same_points(left: Any, right: Any) -> bool:
    a, b = _points(left), _points(right)
    return a is not None and b is not None and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9)


def _aggregate(results: list[ItemResult], missing: list[str], extra: list[str]) -> str:
    if missing or any(r.status == MISSING for r in results):
        return MISSING
    if extra or any(r.status == DIFF for r in results):
        return DIFF
    return MATCH


def _notes(results: list[ItemResult]) -> str:
    notes: list[str] = []
    for result in results:
        if result.note and result.note not in notes:
            notes.append(result.note)
    return " ".join(notes)


def _module_item_status(expected: dict[str, Any], actual: dict[str, Any] | None) -> tuple[str, str]:
    if actual is None:
        return MISSING, "모듈 아이템에 없습니다."
    etype = str(expected.get("type") or "")
    atype = _type_text(actual.get("type"))
    low = atype.lower()
    if etype in PAGE_TYPES:
        if low in ("page", "wikipage"):
            return MATCH, ""
        if low == "file":
            # 페이지가 File 로 들어온 차이는 pages 비교에서 노트와 함께 보고한다.
            return MATCH, ""
        return DIFF, f"페이지가 Canvas에서 {atype or '알 수 없는 유형'}으로 가져와졌습니다."
    if etype in DISCUSSION_TYPES:
        if low == "discussion":
            return MATCH, ""
        return DIFF, f"토론이 Canvas에서 {atype or '알 수 없는 유형'}으로 가져와졌습니다."
    if etype in ASSIGNMENT_TYPES:
        if low == "assignment":
            return MATCH, ""
        return DIFF, f"과제가 Canvas에서 {atype or '알 수 없는 유형'}으로 가져와졌습니다."
    if etype in QUIZ_TYPES:
        if low in ("quiz", "assignment"):
            note = "Canvas가 퀴즈를 과제 아이템으로 표시합니다." if low == "assignment" else ""
            return MATCH, note
        return DIFF, f"퀴즈가 Canvas에서 {atype or '알 수 없는 유형'}으로 가져와졌습니다."
    if etype == "file":
        if low == "file":
            return MATCH, ""
        return DIFF, f"파일이 Canvas에서 {atype or '알 수 없는 유형'}으로 가져와졌습니다."
    return (MATCH, "") if low == etype.lower() else (DIFF, f"유형이 {atype or '알 수 없음'}입니다.")


def expected_from_spec(spec: Spec) -> dict[str, list[dict[str, Any]]]:
    """설계서에서 모듈·페이지·토론·과제·퀴즈 기대 목록을 만든다."""
    modules: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    discussions: list[dict[str, Any]] = []
    assignments: list[dict[str, Any]] = []
    quizzes: list[dict[str, Any]] = []
    for unit in spec.units:
        items: list[dict[str, Any]] = []
        for item in unit.get("items", []):
            info = _expected_item(item)
            items.append(info)
            if item["type"] in PAGE_TYPES:
                pages.append(info)
            elif item["type"] in DISCUSSION_TYPES:
                discussions.append(info)
            elif item["type"] in ASSIGNMENT_TYPES:
                assignments.append(info)
            elif item["type"] in QUIZ_TYPES:
                quizzes.append(info)
        modules.append({"title": unit["title"], "items": items})
    return {
        "modules": modules,
        "pages": pages,
        "discussions": discussions,
        "assignments": assignments,
        "quizzes": quizzes,
    }


def _expected_item(item: dict[str, Any]) -> dict[str, Any]:
    info: dict[str, Any] = {"id": item["id"], "title": item["title"], "type": item["type"]}
    grading = item.get("grading", {})
    if grading.get("max") is not None:
        info["points"] = grading["max"]
    if item["type"] in ASSIGNMENT_TYPES:
        types = item.get("submission", {}).get("types", ["text"])
        info["submission_types"] = [SUBMISSION.get(t, t) for t in types]
    return info


def _module_items(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    modules = snapshot.get("modules")
    return [m for m in modules if isinstance(m, dict)] if isinstance(modules, list) else []


def _module_item_index(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for module in _module_items(snapshot):
        items = module.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                index.setdefault(str(item.get("title", "")), item)
    return index


def _compare_modules(
    expected: dict[str, list[dict[str, Any]]], snapshot: dict[str, Any]
) -> Comparison:
    actual_modules = _module_items(snapshot)
    actual_titles = _titles(actual_modules)
    expected_titles = [m["title"] for m in expected["modules"]]
    missing_modules = [t for t in expected_titles if t not in actual_titles]
    extra_modules = [t for t in actual_titles if t not in expected_titles]
    module_results: list[ItemResult] = []
    item_comparisons: list[Comparison] = []

    for module in expected["modules"]:
        title = module["title"]
        actual_module = _find(actual_modules, title)
        if actual_module is None:
            module_results.append(
                ItemResult("module", title, MISSING, expected={"title": title}, missing=[title],
                           note="Canvas 모듈에 단원 제목이 없습니다.")  # fmt: skip
            )
            item_comparisons.append(_compare_module_items(module, None))
            continue
        module_results.append(ItemResult("module", title, MATCH, expected={"title": title}, actual=actual_module))
        item_comparisons.append(_compare_module_items(module, actual_module))

    status = _aggregate(module_results, missing_modules, extra_modules)
    overall = _aggregate(module_results + [r for c in item_comparisons for r in c.results],
                         missing_modules + [m for c in item_comparisons for m in c.missing],
                         extra_modules + [e for c in item_comparisons for e in c.extra])  # fmt: skip
    return Comparison(
        "modules",
        status,
        expected_titles,
        actual_titles,
        missing_modules,
        extra_modules,
        results=module_results,
        items=item_comparisons,
        overall=overall,
    )


def _compare_module_items(module: dict[str, Any], actual_module: dict[str, Any] | None) -> Comparison:
    title = module["title"]
    expected_items = module["items"]
    expected_titles = [i["title"] for i in expected_items]
    actual_items = []
    if actual_module is not None and isinstance(actual_module.get("items"), list):
        actual_items = [i for i in actual_module["items"] if isinstance(i, dict)]
    actual_titles = _titles(actual_items)
    missing = [t for t in expected_titles if t not in actual_titles]
    extra = [t for t in actual_titles if t not in expected_titles]
    results: list[ItemResult] = []
    for expected in expected_items:
        actual = _find(actual_items, expected["title"])
        status, note = _module_item_status(expected, actual)
        results.append(
            ItemResult(
                "module_item",
                expected["title"],
                status,
                expected=expected,
                actual=actual,
                missing=[expected["title"]] if status == MISSING else [],
                note=note,
            )
        )
    return Comparison(
        f"module_items:{title}",
        _aggregate(results, missing, extra),
        expected_titles,
        actual_titles,
        missing,
        extra,
        results=results,
        note=_notes(results),
    )


def _compare_pages(
    expected: list[dict[str, Any]], snapshot: dict[str, Any], module_index: dict[str, dict[str, Any]]
) -> Comparison:
    actual_pages = snapshot.get("pages")
    actual_titles = _titles(actual_pages)
    expected_titles = [e["title"] for e in expected]
    missing: list[str] = []
    extra = [t for t in actual_titles if t not in expected_titles]
    results: list[ItemResult] = []
    for item in expected:
        title = item["title"]
        actual_page = _find(actual_pages, title)
        if actual_page is not None:
            results.append(ItemResult("page", title, MATCH, expected=item, actual=actual_page))
            continue
        module_item = module_index.get(title)
        atype = _type_text(module_item.get("type")) if module_item else ""
        low = atype.lower()
        if module_item is not None and low in ("page", "wikipage"):
            results.append(
                ItemResult("page", title, MATCH, expected=item, actual=module_item,
                           note="페이지 목록에는 없지만 모듈 아이템으로 Page가 있습니다.")  # fmt: skip
            )
        elif module_item is not None and low == "file":
            results.append(ItemResult("page", title, DIFF, expected=item, actual=module_item, note=PAGE_FILE_NOTE))
        else:
            missing.append(title)
            note = "Canvas 페이지 목록과 모듈 아이템에 없습니다."
            results.append(ItemResult("page", title, MISSING, expected=item, missing=[title], note=note))
    return Comparison(
        "pages",
        _aggregate(results, missing, extra),
        expected_titles,
        actual_titles,
        missing,
        extra,
        results=results,
        note=_notes(results),
    )


def _compare_discussions(
    expected: list[dict[str, Any]], snapshot: dict[str, Any], module_index: dict[str, dict[str, Any]]
) -> Comparison:
    actual_discussions = snapshot.get("discussions")
    actual_titles = _titles(actual_discussions)
    expected_titles = [e["title"] for e in expected]
    missing: list[str] = []
    extra = [t for t in actual_titles if t not in expected_titles]
    results: list[ItemResult] = []
    for item in expected:
        title = item["title"]
        actual = _find(actual_discussions, title)
        if actual is None:
            module_item = module_index.get(title)
            if module_item is not None and _type_text(module_item.get("type")).lower() == "discussion":
                results.append(
                    ItemResult("discussion", title, DIFF, expected=item, actual=module_item,
                               note="모듈 아이템에는 있지만 토론 목록에 없습니다.")  # fmt: skip
                )
            else:
                missing.append(title)
                results.append(
                    ItemResult("discussion", title, MISSING, expected=item, missing=[title],
                               note="Canvas 토론 목록에 없습니다.")  # fmt: skip
                )
            continue
        expected_points = item.get("points")
        actual_points = actual.get("points_possible")
        if expected_points is not None and actual_points is None:
            results.append(
                ItemResult("discussion", title, DIFF, expected=item, actual=actual, note=DISCUSSION_POINTS_NOTE)
            )
        elif expected_points is not None and not _same_points(actual_points, expected_points):
            results.append(
                ItemResult("discussion", title, DIFF, expected=item, actual=actual,
                           note=f"점수가 설계서 {expected_points}점과 다릅니다 (Canvas {actual_points}).")  # fmt: skip
            )
        else:
            results.append(ItemResult("discussion", title, MATCH, expected=item, actual=actual))
    return Comparison(
        "discussions",
        _aggregate(results, missing, extra),
        expected_titles,
        actual_titles,
        missing,
        extra,
        results=results,
        note=_notes(results),
    )


def _compare_assignments(
    expected: list[dict[str, Any]], snapshot: dict[str, Any], module_index: dict[str, dict[str, Any]]
) -> Comparison:
    actual_assignments = snapshot.get("assignments")
    actual_titles = _titles(actual_assignments)
    expected_titles = [e["title"] for e in expected]
    missing: list[str] = []
    extra = [t for t in actual_titles if t not in expected_titles]
    results: list[ItemResult] = []
    for item in expected:
        title = item["title"]
        actual = _find(actual_assignments, title)
        if actual is None:
            module_item = module_index.get(title)
            if module_item is not None and _type_text(module_item.get("type")).lower() == "assignment":
                results.append(
                    ItemResult("assignment", title, DIFF, expected=item, actual=module_item,
                               note="모듈 아이템에는 있지만 과제 목록에 없습니다.")  # fmt: skip
                )
            else:
                missing.append(title)
                results.append(
                    ItemResult("assignment", title, MISSING, expected=item, missing=[title],
                               note="Canvas 과제 목록에 없습니다.")  # fmt: skip
                )
            continue
        problems: list[str] = []
        expected_types = set(item.get("submission_types", []))
        actual_types = _type_set(actual.get("type"))
        if expected_types and actual_types and not expected_types.issubset(actual_types):
            absent = ", ".join(sorted(expected_types - actual_types))
            problems.append(f"제출 유형({absent})이 없습니다.")
        expected_points = item.get("points")
        actual_points = actual.get("points_possible")
        if expected_points is not None and actual_points is None:
            problems.append("점수가 없습니다.")
        elif expected_points is not None and not _same_points(actual_points, expected_points):
            problems.append(f"점수가 설계서 {expected_points}점과 다릅니다 (Canvas {actual_points}).")
        status = DIFF if problems else MATCH
        results.append(
            ItemResult("assignment", title, status, expected=item, actual=actual, note=" ".join(problems))
        )
    return Comparison(
        "assignments",
        _aggregate(results, missing, extra),
        expected_titles,
        actual_titles,
        missing,
        extra,
        results=results,
        note=_notes(results),
    )


def _compare_quizzes(
    expected: list[dict[str, Any]], snapshot: dict[str, Any], module_index: dict[str, dict[str, Any]]
) -> Comparison:
    actual_quizzes = snapshot.get("quizzes")
    actual_titles = _titles(actual_quizzes)
    assignment_titles = set(_titles(snapshot.get("assignments")))
    expected_titles = [e["title"] for e in expected]
    missing: list[str] = []
    extra = [t for t in actual_titles if t not in expected_titles]
    results: list[ItemResult] = []
    for item in expected:
        title = item["title"]
        actual = _find(actual_quizzes, title)
        if actual is not None:
            results.append(ItemResult("quiz", title, MATCH, expected=item, actual=actual))
        elif title in assignment_titles:
            results.append(
                ItemResult("quiz", title, DIFF, expected=item, actual=_find(snapshot.get("assignments"), title),
                           note="퀴즈가 Canvas 과제 목록으로 가져와졌습니다.")  # fmt: skip
            )
        elif title in module_index:
            results.append(
                ItemResult("quiz", title, DIFF, expected=item, actual=module_index[title],
                           note="퀴즈가 모듈 아이템으로만 있습니다.")  # fmt: skip
            )
        else:
            missing.append(title)
            results.append(ItemResult("quiz", title, MISSING, expected=item, missing=[title], note=QUIZ_MISSING_NOTE))
    return Comparison(
        "quizzes",
        _aggregate(results, missing, extra),
        expected_titles,
        actual_titles,
        missing,
        extra,
        results=results,
        note=_notes(results),
    )


def cc_limitations(spec: Spec) -> list[Conversion]:
    """표준 CC 1.3 패키지에 담기지 않는 과정 수준 정보를 내보내기와 같은 문구로 보고한다."""
    notes: list[Conversion] = []
    items = [item for _, _, item in spec.iter_items()]
    if any(item.get(k) for item in items for k in ("opens_day", "due_day", "cutoff_day")):
        notes.append(
            Conversion(
                "course",
                "info",
                "공개일·마감일은 표준 CC 1.3에 없어 패키지에 날짜로 들어가지 않습니다 (본문 힌트만 포함).",
            )
        )
    if any(item.get("completion", {}).get("mode", "none") != "none" for item in items):
        notes.append(Conversion("course", "info", "완료 조건은 표준 CC 1.3에 없어 패키지에 포함되지 않습니다."))
    if any(item.get("requires") for item in items) or any(unit.get("requires") for unit in spec.units):
        notes.append(Conversion("course", "info", "선수조건은 표준 CC 1.3에 없어 패키지에 포함되지 않습니다."))
    if spec.categories:
        notes.append(Conversion("grading", "info", "성적 카테고리와 가중치는 표준 CC 1.3에 없어 패키지에 포함되지 않습니다."))
    return notes


def _is_absolute(path: str) -> bool:
    return bool(URL_SCHEME.match(path)) or path.startswith("//")


def parse_verify_steps(raw: Any) -> list[StepReport]:
    """verify=True 단계 실행 결과를 읽는다. 절대 URL path 는 오류로 거절한다."""
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError("verify-steps 는 JSON 배열이어야 합니다.")
    reports: list[StepReport] = []
    for index, entry in enumerate(raw, 1):
        if not isinstance(entry, dict):
            reports.append(StepReport(f"단계 {index}", "", "", None, "오류", "단계 항목이 객체가 아닙니다."))
            continue
        about = str(entry.get("about") or f"단계 {index}")
        method = str(entry.get("method") or "")
        path = entry.get("path_template")
        status = entry.get("status")
        error = entry.get("error")
        if not isinstance(path, str) or not path:
            reports.append(StepReport(about, method, "", None, "오류", "path_template 이 없습니다."))
            continue
        if _is_absolute(path):
            reports.append(StepReport(about, method, path, None, "오류", "절대 URL은 허용하지 않습니다."))
            continue
        if isinstance(status, bool) or not isinstance(status, int):
            note = str(error) if error else "응답 상태가 없습니다."
            reports.append(StepReport(about, method, path, None, "실패", note))
        elif 200 <= status < 300:
            reports.append(StepReport(about, method, path, status, "통과"))
        else:
            note = str(error) if error else f"HTTP {status}"
            reports.append(StepReport(about, method, path, status, "실패", note))
    return reports


def verify_canvas(spec: Spec, snapshot: Any, verify_steps: Any = None) -> CanvasVerifyResult:
    """설계서와 Canvas 스냅샷을 비교한다. 네트워크를 쓰지 않는다."""
    if not isinstance(snapshot, dict):
        raise ValueError("스냅샷은 JSON 객체여야 합니다.")
    expected = expected_from_spec(spec)
    module_index = _module_item_index(snapshot)
    comparisons = [
        _compare_modules(expected, snapshot),
        _compare_pages(expected["pages"], snapshot, module_index),
        _compare_discussions(expected["discussions"], snapshot, module_index),
        _compare_assignments(expected["assignments"], snapshot, module_index),
        _compare_quizzes(expected["quizzes"], snapshot, module_index),
    ]
    return CanvasVerifyResult(
        spec_id=spec.id,
        spec_version=spec.data.get("version"),
        comparisons=comparisons,
        conversions=cc_limitations(spec),
        steps=parse_verify_steps(verify_steps),
    )
