"""배포 계획(Plan): 퍼블리셔가 만드는 실행 전 변경 목록.

계획은 네트워크 호출 없이 만들어지며, 실행기(에이전트·허브)가 단계를 순서대로 실행한다.
앞 단계 결과는 `binds` 로 이름을 얻고, 뒤 단계 인자는 "${이름}" 으로 그 값을 참조한다.

    {"tool": "create_quiz", "args": {...}, "binds": {"w1-quiz.cmid": "cmid"}}
    {"tool": "add_quiz_questions", "args": {"quiz_id": "${w1-quiz.instance}", ...}}
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

Severity = Literal["info", "warn", "loss"]
REF_RE = re.compile(r"^\$\{([^}]+)\}$")
INLINE_REF_RE = re.compile(r"\$\{([^}]+)\}")


@dataclass
class Step:
    tool: str
    args: dict[str, Any]
    about: str
    binds: dict[str, str] = field(default_factory=dict)
    verify: bool = False  # 공식 문서로 아직 검증하지 않은 호출 형식

    def to_dict(self, index: int) -> dict[str, Any]:
        d = {"n": index, **asdict(self)}
        if not d["binds"]:
            del d["binds"]
        if not d["verify"]:
            del d["verify"]
        return d


@dataclass(frozen=True)
class Conversion:
    """설계서와 대상 LMS 사이에서 생기는 변환·손실. 교수자가 알고 승인해야 한다."""

    where: str
    severity: Severity
    message: str


@dataclass
class Plan:
    target: str
    spec_id: str
    spec_version: str | None
    start: str
    steps: list[Step] = field(default_factory=list)
    conversions: list[Conversion] = field(default_factory=list)

    def add(self, tool: str, args: dict[str, Any], about: str, **kw: Any) -> Step:
        step = Step(tool, {k: v for k, v in args.items() if v is not None}, about, **kw)
        self.steps.append(step)
        return step

    def note(self, where: str, severity: Severity, message: str) -> None:
        c = Conversion(where, severity, message)
        if c not in self.conversions:
            self.conversions.append(c)

    def to_dict(self) -> dict[str, Any]:
        counts = {s: sum(c.severity == s for c in self.conversions) for s in ("info", "warn", "loss")}
        return {
            "target": self.target,
            "spec": {"id": self.spec_id, "version": self.spec_version},
            "start": self.start,
            "summary": {"steps": len(self.steps), "conversions": counts},
            "conversions": [asdict(c) for c in self.conversions],
            "steps": [s.to_dict(i) for i, s in enumerate(self.steps, 1)],
        }

    def to_text(self) -> str:
        lines = [f"배포 계획 → {self.target}  (설계서 {self.spec_id} {self.spec_version or ''}, 시작일 {self.start})", ""]
        if self.conversions:
            lines.append("변환 보고서")
            mark = {"info": "  ·", "warn": "  !", "loss": "  ✗"}
            for c in self.conversions:
                lines.append(f"{mark[c.severity]} [{c.where}] {c.message}")
            lines.append("")
        lines.append(f"실행 단계 {len(self.steps)}개")
        for i, s in enumerate(self.steps, 1):
            flag = "  (형식 검증 필요)" if s.verify else ""
            lines.append(f"  {i:>3}. {s.tool:<28} {s.about}{flag}")
        return "\n".join(lines)


def resolve(value: Any, bound: dict[str, Any]) -> Any:
    """인자 안의 "${이름}" 을 실행 중 쌓인 값으로 바꾼다. 실행기가 각 단계 직전에 호출한다.

    문자열 전체가 참조이면 값의 원래 타입(int 등)을 유지하고, 경로처럼 문자열 안에 섞여 있으면 문자열로 치환한다.
    """
    if isinstance(value, str):
        m = REF_RE.match(value)
        if m:
            if m.group(1) not in bound:
                raise KeyError(f"아직 값이 없는 참조: {m.group(1)}")
            return bound[m.group(1)]

        def sub(mm: re.Match[str]) -> str:
            if mm.group(1) not in bound:
                raise KeyError(f"아직 값이 없는 참조: {mm.group(1)}")
            return str(bound[mm.group(1)])

        return INLINE_REF_RE.sub(sub, value)
    if isinstance(value, list):
        return [resolve(v, bound) for v in value]
    if isinstance(value, dict):
        return {k: resolve(v, bound) for k, v in value.items()}
    return value


def collect(step: Step, result: dict[str, Any], bound: dict[str, Any]) -> None:
    """단계 결과에서 binds 가 가리키는 값을 꺼내 bound 에 넣는다. 경로는 점으로 구분."""
    for name, path in step.binds.items():
        value: Any = result
        for part in path.split("."):
            value = value[int(part)] if isinstance(value, list) else value[part]
        bound[name] = value
