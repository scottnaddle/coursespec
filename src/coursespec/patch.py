"""검증된 JSON Patch 편집 (RFC 6902의 add·replace·remove·test).

설계 에이전트는 설계서를 통째로 다시 쓰지 않고 패치로 고친다. 패치는 적용 후
스키마 검증과 린트(오류 E)를 모두 통과해야만 파일에 기록되며, YAML 주석과 순서는 보존된다.
OpenMAIC 워크벤치의 "Edit with AI"(검증된 JSON Patch)와 같은 방식이다.
"""

from __future__ import annotations

import copy
import io
import json
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from .lint import Finding, lint
from .spec import SpecError, from_data


class PatchError(Exception):
    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def _tokens(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise PatchError(f"JSON Pointer 는 '/'로 시작해야 합니다: {pointer}")
    return [t.replace("~1", "/").replace("~0", "~") for t in pointer[1:].split("/")]


def _parent(doc: Any, pointer: str) -> tuple[Any, str]:
    tokens = _tokens(pointer)
    if not tokens:
        raise PatchError("문서 전체는 바꿀 수 없습니다.")
    node = doc
    for t in tokens[:-1]:
        node = _child(node, t, pointer)
    return node, tokens[-1]


def _child(node: Any, token: str, pointer: str) -> Any:
    try:
        if isinstance(node, list):
            return node[int(token)]
        return node[token]
    except (KeyError, IndexError, ValueError, TypeError):
        raise PatchError(f"경로가 없습니다: {pointer}") from None


def _plain(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def apply_ops(doc: Any, ops: list[dict[str, Any]]) -> Any:
    """ops 를 doc 에 적용한다. doc 은 바뀌지 않고 새 문서를 돌려준다."""
    doc = copy.deepcopy(doc)
    for i, op in enumerate(ops, 1):
        kind, path = op.get("op"), op.get("path")
        if not isinstance(path, str):
            raise PatchError(f"{i}번째 연산에 path 가 없습니다.")
        if kind == "test":
            node = doc
            for t in _tokens(path):
                node = _child(node, t, path)
            if _plain(node) != _plain(op.get("value")):
                raise PatchError(f"{i}번째 test 실패: {path} 의 값이 예상과 다릅니다.")
            continue
        parent, key = _parent(doc, path)
        if kind == "add":
            if isinstance(parent, list):
                if key == "-":
                    parent.append(op["value"])
                else:
                    parent.insert(int(key), op["value"])
            else:
                parent[key] = op["value"]
        elif kind == "replace":
            _child(parent, key, path)
            parent[int(key) if isinstance(parent, list) else key] = op["value"]
        elif kind == "remove":
            _child(parent, key, path)
            del parent[int(key) if isinstance(parent, list) else key]
        else:
            raise PatchError(f"{i}번째 연산 '{kind}'은 지원하지 않습니다 (add·replace·remove·test).")
    return doc


def patch_file(path: str | Path, ops: list[dict[str, Any]], dry_run: bool = False) -> list[Finding]:
    """패치를 적용하고 검증을 통과하면 파일에 쓴다. 남은 경고를 돌려준다."""
    p = Path(path)
    is_json = p.suffix == ".json"
    text = p.read_text("utf-8")
    original = json.loads(text) if is_json else _yaml().load(text)
    patched = apply_ops(original, ops)

    try:
        spec = from_data(_plain(patched), p)
    except SpecError as exc:
        raise PatchError("패치 결과가 스키마를 통과하지 못했습니다.", exc.errors) from exc
    findings = lint(spec)
    errors = [f for f in findings if f.is_error]
    if errors:
        raise PatchError("패치 결과에 린트 오류가 있습니다.", [str(f) for f in errors])

    if not dry_run:
        if is_json:
            p.write_text(json.dumps(patched, ensure_ascii=False, indent=2) + "\n", "utf-8")
        else:
            buf = io.StringIO()
            _yaml().dump(patched, buf)
            p.write_text(buf.getvalue(), "utf-8")
    return findings
