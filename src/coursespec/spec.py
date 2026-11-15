"""설계서 로딩, 스키마 검증, 색인."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Iterator

import yaml
from jsonschema import Draft202012Validator

CORE_TYPES = ("page", "file", "assignment", "quiz", "discussion")
EXTENDED_TYPES = ("peer_review", "wiki", "glossary", "survey", "h5p", "interactive_lecture")


class SpecError(Exception):
    """설계서를 읽을 수 없거나 스키마에 맞지 않을 때."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


@lru_cache(maxsize=1)
def schema() -> dict[str, Any]:
    """패키지에 포함된 스키마를 읽고, 소스 체크아웃에서는 저장소의 schema/ 를 읽는다."""
    try:
        text = resources.files("coursespec").joinpath("coursespec.schema.json").read_text("utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        repo = Path(__file__).resolve().parents[2] / "schema" / "coursespec.schema.json"
        text = repo.read_text("utf-8")
    return json.loads(text)


def schema_errors(data: Any) -> list[str]:
    validator = Draft202012Validator(schema())
    out = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(root)"
        out.append(f"{where}: {err.message}")
    return out


@dataclass
class Spec:
    """검증된 설계서와 id 색인."""

    data: dict[str, Any]
    path: Path | None = None
    items: dict[str, dict[str, Any]] = field(init=False)
    unit_of: dict[str, str] = field(init=False)
    unit_index: dict[str, int] = field(init=False)
    pointer: dict[str, str] = field(init=False)
    materials: dict[str, dict[str, Any]] = field(init=False)

    def __post_init__(self) -> None:
        self.items = {}
        self.unit_of = {}
        self.unit_index = {}
        self.pointer = {}
        for i, unit in enumerate(self.units):
            self.unit_index[unit["id"]] = i
            for j, item in enumerate(unit.get("items", [])):
                self.items.setdefault(item["id"], item)
                self.unit_of.setdefault(item["id"], unit["id"])
                self.pointer.setdefault(item["id"], f"/units/{i}/items/{j}")
        self.materials = {}
        for m in self.data.get("materials", []):
            self.materials.setdefault(m["id"], m)

    @property
    def id(self) -> str:
        return self.data["id"]

    @property
    def units(self) -> list[dict[str, Any]]:
        return self.data["units"]

    @property
    def outcomes(self) -> list[dict[str, Any]]:
        return self.data.get("outcomes", [])

    @property
    def title(self) -> str:
        return self.data["title"]

    @property
    def categories(self) -> list[dict[str, Any]]:
        return self.data.get("grading", {}).get("categories", [])

    @property
    def badges(self) -> list[dict[str, Any]]:
        return self.data.get("badges", [])

    @property
    def timezone(self) -> str:
        return self.data.get("timezone", "Asia/Seoul")

    def iter_items(self) -> Iterator[tuple[int, dict[str, Any], dict[str, Any]]]:
        """(단원 순서, 단원, 활동)을 설계서 순서대로."""
        for i, unit in enumerate(self.units):
            for item in unit.get("items", []):
                yield i, unit, item

    def external_id(self, item_id: str) -> str:
        """LMS 쪽 ID number 에 심는 값. 재배포 때 같은 활동을 찾는 열쇠."""
        return f"cs:{self.id}:{item_id}"


def read_data(path: str | Path) -> Any:
    p = Path(path)
    try:
        text = p.read_text("utf-8")
    except OSError as exc:
        raise SpecError(f"읽을 수 없습니다: {p} ({exc})") from exc
    try:
        return json.loads(text) if p.suffix == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise SpecError(f"구문 오류: {p} ({exc})") from exc


def load_spec(path: str | Path) -> Spec:
    return from_data(read_data(path), Path(path))


def from_data(data: Any, path: Path | None = None) -> Spec:
    errors = schema_errors(data)
    if errors:
        raise SpecError(f"스키마 오류 {len(errors)}건", errors)
    return Spec(data, path)
