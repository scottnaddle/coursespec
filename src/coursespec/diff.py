"""설계서와 LMS 스냅샷의 차이(diff) 계획.

퍼블리셔와 마찬가지로 네트워크를 호출하지 않는다. 실행기(에이전트·허브)가 읽어 온
`get_course_outline`·`gradebook_overview` JSON 과 마지막 배포 기록(record)을 입력으로 받아
생성·수정·숨김 단계를 만든다. 삭제 단계는 절대 만들지 않는다.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from .plan import Conversion, Severity, Step
from .publishers.moodle import plan_item_steps
from .spec import Spec

# 설계서 활동 유형 → Moodle modname
MODNAME = {
    "page": "page",
    "file": "resource",
    "assignment": "assign",
    "quiz": "quiz",
    "discussion": "forum",
    "peer_review": "workshop",
    "wiki": "wiki",
    "glossary": "glossary",
    "survey": "feedback",
    "h5p": "h5pactivity",
    "interactive_lecture": "openmaic",
}

ANNOUNCEMENT_NAMES = {
    "강좌공지",
    "공지사항",
    "공지",
    "announcements",
    "announcement",
    "announcements forum",
    "news forum",
}
ANNOUNCEMENT_MODNAMES = {"forum"}


@dataclass(frozen=True)
class Drift:
    """마지막 배포 이후 LMS에서 직접 바뀐 값. blocked 이면 덮어쓰지 않는다."""

    where: str
    field: str
    lms: Any
    last_deployed: Any
    spec: Any
    blocked: bool


@dataclass
class DiffResult:
    spec_id: str
    spec_version: str | None
    start: str
    course_id: int
    steps: list[Step] = field(default_factory=list)
    conversions: list[Conversion] = field(default_factory=list)
    drifts: list[Drift] = field(default_factory=list)
    record: dict[str, Any] = field(default_factory=dict)
    unmatched: list[str] = field(default_factory=list)
    actions: dict[str, int] = field(default_factory=lambda: {"create": 0, "update": 0, "hide": 0})

    def add(self, tool: str, args: dict[str, Any], about: str, **kw: Any) -> Step:
        step = Step(tool, {k: v for k, v in args.items() if v is not None}, about, **kw)
        self.steps.append(step)
        return step

    def note(self, where: str, severity: Severity, message: str) -> None:
        c = Conversion(where, severity, message)
        if c not in self.conversions:
            self.conversions.append(c)

    def drift(self, where: str, field_name: str, lms: Any, last: Any, spec: Any, blocked: bool) -> None:
        d = Drift(where, field_name, lms, last, spec, blocked)
        if d not in self.drifts:
            self.drifts.append(d)

    @property
    def blocked(self) -> bool:
        return any(d.blocked for d in self.drifts)

    def to_dict(self) -> dict[str, Any]:
        counts = {s: sum(c.severity == s for c in self.conversions) for s in ("info", "warn", "loss")}
        blocked = sum(d.blocked for d in self.drifts)
        return {
            "target": "moodle",
            "spec": {"id": self.spec_id, "version": self.spec_version},
            "start": self.start,
            "course_id": self.course_id,
            "summary": {
                "steps": len(self.steps),
                "conversions": counts,
                "drifts": len(self.drifts),
                "blocked": blocked,
                "actions": dict(self.actions),
            },
            "conversions": [asdict(c) for c in self.conversions],
            "drifts": [asdict(d) for d in self.drifts],
            "unmatched": list(self.unmatched),
            "steps": [s.to_dict(i) for i, s in enumerate(self.steps, 1)],
            "record": self.record,
            "suggested_record": self.record,
        }

    def to_text(self) -> str:
        lines = [
            f"차이 계획 → moodle 강좌 {self.course_id}  "
            f"(설계서 {self.spec_id} {self.spec_version or ''}, 시작일 {self.start})",
            "",
        ]
        if self.conversions:
            lines.append("변환 보고서")
            mark = {"info": "  ·", "warn": "  !", "loss": "  ✗"}
            for c in self.conversions:
                lines.append(f"{mark[c.severity]} [{c.where}] {c.message}")
            lines.append("")
        if self.drifts:
            lines.append("드리프트")
            for d in self.drifts:
                flag = "  (차단됨: --accept-drift 필요)" if d.blocked else ""
                lines.append(
                    f"  ! [{d.where}] {d.field}: LMS={d.lms!r}, "
                    f"마지막 배포={d.last_deployed!r}, 설계={d.spec!r}{flag}"
                )
            lines.append("")
        lines.append(f"실행 단계 {len(self.steps)}개")
        for i, s in enumerate(self.steps, 1):
            flag = "  (형식 검증 필요)" if s.verify else ""
            lines.append(f"  {i:>3}. {s.tool:<28} {s.about}{flag}")
        return "\n".join(lines)


def _int(value: Any) -> Any:
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _parse_outline(outline: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """`get_course_outline` 결과를 모듈 목록과 섹션 메타로 나눈다.

    `{"sections": [...]}` 와 섹션 배열 자체를 모두 받는다.
    """
    if isinstance(outline, dict):
        sections = outline.get("sections") or []
    elif isinstance(outline, list):
        sections = outline
    else:
        sections = []
    modules: list[dict[str, Any]] = []
    meta: list[dict[str, Any]] = []
    for i, sec in enumerate(sections):
        if not isinstance(sec, dict):
            continue
        sec_no = _int(sec.get("section", i))
        meta.append({"section": sec_no, "name": str(sec.get("name") or "")})
        for mod in sec.get("modules") or []:
            if not isinstance(mod, dict):
                continue
            modules.append(
                {
                    "cmid": _int(mod.get("id", mod.get("cmid"))),
                    "name": str(mod.get("name") or ""),
                    "modname": str(mod.get("modname") or ""),
                    "instance": mod.get("instance"),
                    "visible": mod.get("visible", mod.get("visibleoncoursepage")),
                    "section": _int(mod.get("section", sec_no)),
                    "idnumber": mod.get("idnumber") or mod.get("cmidnumber"),
                }
            )
    return modules, meta


def _grade_items(gradebook: Any) -> list[dict[str, Any]]:
    if not isinstance(gradebook, dict):
        return []
    rows: list[dict[str, Any]] = []
    usergrades = gradebook.get("usergrades")
    if isinstance(usergrades, list):
        for entry in usergrades:
            if isinstance(entry, dict):
                rows.extend(entry.get("gradeitems") or entry.get("grade_items") or [])
    for key in ("gradeitems", "grade_items"):
        value = gradebook.get(key)
        if isinstance(value, list):
            rows.extend(value)
    return [r for r in rows if isinstance(r, dict)]


def _record_cmids(record: dict[str, Any]) -> dict[str, Any]:
    """record 의 bound/items 에서 활동 id → cmid 를 모은다."""
    out: dict[str, Any] = {}
    bound = record.get("bound")
    if isinstance(bound, dict):
        for key, value in bound.items():
            if key.endswith(".cmid"):
                out[key.rsplit(".cmid", 1)[0]] = _int(value)
    items = record.get("items")
    if isinstance(items, dict):
        for iid, info in items.items():
            if isinstance(info, dict) and info.get("cmid") is not None:
                out.setdefault(iid, _int(info["cmid"]))
    return out


def _last_name(record: dict[str, Any], iid: str) -> Any:
    items = record.get("items")
    if not isinstance(items, dict):
        return None
    info = items.get(iid)
    return info.get("name") if isinstance(info, dict) else None


def _is_announcements(module: dict[str, Any], recorded: bool, has_cs_id: bool) -> bool:
    """섹션 0 의 기본 공지 포럼은 CourseSpec 이 만든 활동이 아니므로 건드리지 않는다."""
    if module.get("section") != 0:
        return False
    name = str(module.get("name") or "").strip().lower()
    if name in ANNOUNCEMENT_NAMES:
        return True
    return (
        str(module.get("modname") or "") in ANNOUNCEMENT_MODNAMES
        and not recorded
        and not has_cs_id
    )


def _unit_sections(spec: Spec, meta: list[dict[str, Any]], record: dict[str, Any]) -> dict[str, Any]:
    bound = record.get("bound") if isinstance(record.get("bound"), dict) else {}
    by_name = {m["name"]: m["section"] for m in meta if m.get("name")}
    out: dict[str, Any] = {}
    for i, unit in enumerate(spec.units):
        key = f"{unit['id']}.section"
        if key in bound:
            out[unit["id"]] = _int(bound[key])
        elif unit["title"] in by_name:
            out[unit["id"]] = by_name[unit["title"]]
        else:
            out[unit["id"]] = i + 1
    return out


def diff_moodle(
    spec: Spec,
    start: date,
    course_id: int,
    outline: Any,
    gradebook: Any = None,
    record: dict[str, Any] | None = None,
    accept_drift: bool = False,
) -> DiffResult:
    """설계서와 LMS 스냅샷을 비교한다. 기존 강좌만 다루며 create_course 는 만들지 않는다."""
    record = record or {}
    result = DiffResult(
        spec_id=spec.id,
        spec_version=spec.data.get("version"),
        start=start.isoformat(),
        course_id=course_id,
    )
    modules, meta = _parse_outline(outline)
    grade_items = _grade_items(gradebook)
    grade_by_cmid = {_int(g.get("cmid")): g for g in grade_items if g.get("cmid") is not None}
    record_cmid = _record_cmids(record)
    record_iid = {_int(cmid): iid for iid, cmid in record_cmid.items()}
    sections = _unit_sections(spec, meta, record)

    # ID number 는 outline 보다 gradebook 에 더 자주 있다. 둘을 합쳐 cmid 로 찾는다.
    idnumber_by_cmid: dict[Any, str] = {}
    for cmid, g in grade_by_cmid.items():
        idn = g.get("idnumber")
        if idn:
            idnumber_by_cmid[cmid] = str(idn).strip()
    for m in modules:
        if m["idnumber"]:
            idnumber_by_cmid[m["cmid"]] = str(m["idnumber"]).strip()
    cmid_by_idnumber = {idn: cmid for cmid, idn in idnumber_by_cmid.items()}

    module_by_cmid = {m["cmid"]: m for m in modules if m.get("cmid") is not None}
    matched: dict[str, dict[str, Any]] = {}
    matched_cmids: set[Any] = set()
    ambiguous: set[str] = set()

    for _, unit, item in spec.iter_items():
        iid = item["id"]
        module: dict[str, Any] | None = None

        # 1) cs:<spec.id>:<item.id> ID number (gradebook 또는 outline)
        ext = spec.external_id(iid)
        cmid = cmid_by_idnumber.get(ext)
        if cmid is not None:
            module = module_by_cmid.get(cmid)
            if module is None and cmid in grade_by_cmid:
                g = grade_by_cmid[cmid]
                module = {
                    "cmid": cmid,
                    "name": str(g.get("itemname") or ""),
                    "modname": str(g.get("itemmodule") or ""),
                    "instance": None,
                    "visible": None,
                    "section": None,
                    "idnumber": ext,
                }

        # 2) 마지막 배포 기록의 cmid
        if module is None and iid in record_cmid:
            module = module_by_cmid.get(record_cmid[iid])

        # 3) 같은 섹션·modname·현재 이름이 정확히 하나일 때만
        if module is None:
            modname = MODNAME.get(item["type"])
            candidates = [
                m for m in modules
                if m["cmid"] not in matched_cmids
                and m["modname"] == modname
                and m["name"] == item["title"]
                and m["section"] == sections[unit["id"]]
            ]
            if len(candidates) == 1:
                module = candidates[0]
            elif len(candidates) > 1:
                ambiguous.add(iid)
                result.note(
                    iid,
                    "warn",
                    "같은 섹션에 이름과 유형이 같은 활동이 여러 개라 어떤 활동인지 고르지 않았습니다. "
                    "ID number 또는 배포 기록이 있어야 안전하게 수정할 수 있습니다.",
                )

        if module is not None:
            matched[iid] = module
            matched_cmids.add(module["cmid"])

    # 생성: 설계서에 있고 LMS 에 없으며, 동명 후보가 모호하지 않은 활동
    for _, unit, item in spec.iter_items():
        iid = item["id"]
        if iid in matched or iid in ambiguous:
            continue
        steps = plan_item_steps(spec, start, course_id, sections[unit["id"]], item)
        result.steps.extend(steps.steps)
        result.conversions.extend(c for c in steps.conversions if c not in result.conversions)
        result.actions["create"] += 1

    # 수정: 매칭된 활동의 이름이 설계서와 다를 때. 마지막 배포 기록과 다르면 드리프트.
    for iid, module in matched.items():
        item = spec.items[iid]
        lms_name = module["name"]
        spec_name = item["title"]
        last = _last_name(record, iid)
        drifted = last is not None and lms_name != last
        if drifted:
            blocked = not accept_drift
            result.drift(iid, "name", lms_name, last, spec_name, blocked)
        if lms_name != spec_name:
            if drifted and not accept_drift:
                continue
            result.add(
                "update_activity",
                {"cmid": module["cmid"], "name": spec_name},
                f"활동 이름 변경: {iid}",
            )
            result.actions["update"] += 1

    # 숨김/정보: LMS 에만 남은 활동. 삭제는 하지 않는다.
    for module in modules:
        cmid = module["cmid"]
        if cmid in matched_cmids:
            continue
        idn = idnumber_by_cmid.get(cmid) or (str(module["idnumber"]).strip() if module["idnumber"] else "")
        cs_iid = None
        prefix = f"cs:{spec.id}:"
        if idn.startswith(prefix):
            cs_iid = idn[len(prefix):]
        rec_iid = record_iid.get(cmid)
        previous = bool(cs_iid) or rec_iid is not None
        removed_iid = cs_iid or rec_iid
        is_announcements = _is_announcements(module, recorded=rec_iid is not None, has_cs_id=bool(cs_iid))

        if previous and removed_iid not in spec.items:
            if is_announcements:
                result.note(
                    removed_iid or str(cmid),
                    "info",
                    "LMS 기본 공지 포럼으로 보여 숨기지 않습니다. 설계서에 없는 활동입니다.",
                )
                continue
            last = _last_name(record, removed_iid) if removed_iid else None
            drifted = last is not None and module["name"] != last
            if drifted:
                blocked = not accept_drift
                result.drift(removed_iid or str(cmid), "name", module["name"], last, None, blocked)
                if blocked:
                    continue
            if module["visible"] in (0, False, "0"):
                result.note(removed_iid or str(cmid), "info", "이미 숨겨진 이전 활동입니다.")
                continue
            result.add(
                "set_activity_visibility",
                {"cmid": cmid, "visible": False},
                f"이전 활동 숨김: {removed_iid or cmid} ({module['name']})",
            )
            result.actions["hide"] += 1
            continue

        if is_announcements:
            result.note(
                removed_iid or str(cmid),
                "info",
                "LMS 기본 공지 포럼으로 보여 숨기지 않습니다. 설계서에 없는 활동입니다.",
            )
        else:
            result.note(
                removed_iid or str(cmid),
                "info",
                f"LMS에만 있는 활동 '{module['name']}'은 CourseSpec 활동으로 확인되지 않아 그대로 둡니다.",
            )

    # 실행기가 apply 성공 뒤 기록할 스냅샷. 호스트 이름은 넣지 않는다.
    bound: dict[str, Any] = {"course.id": course_id}
    items: dict[str, Any] = {}
    for iid, module in matched.items():
        item = spec.items[iid]
        idn = idnumber_by_cmid.get(module["cmid"]) or spec.external_id(iid)
        info: dict[str, Any] = {
            "cmid": module["cmid"],
            "name": item["title"],
            "modname": module["modname"] or MODNAME.get(item["type"], ""),
        }
        if idn:
            info["idnumber"] = idn
        items[iid] = info
        bound[f"{iid}.cmid"] = module["cmid"]
        if module.get("instance") is not None:
            bound[f"{iid}.instance"] = module["instance"]
    result.record = {
        "spec_id": spec.id,
        "spec_version": spec.data.get("version"),
        "target": "moodle",
        "course_id": course_id,
        "start": start.isoformat(),
        "bound": bound,
        "items": items,
    }
    result.unmatched = sorted(ambiguous)

    return result
