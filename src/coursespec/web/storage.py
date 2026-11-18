"""서버 쪽 작업 공간에 과정 초안·설계서를 YAML 로 저장·조회한다.

API·화면은 구조화된 JSON 만 주고받고, 저장 형식만 YAML 이다. 교수 화면에 YAML 은
보여 주지 않는다. 작업 공간 경로는 환경변수 `COURSESPEC_WEB_WORKSPACE`(없으면 저장소
로컬 `var/workspace`, gitignore)를 쓴다. 설계서는 `designs/` 아래에 두고, 수정 요청
검증 패치와 확정 상태는 설계서 옆 파일로 함께 둔다.
"""

from __future__ import annotations

import copy
import io
import json
import os
import re
import shutil
from pathlib import Path

import yaml
from ruamel.yaml import YAML

from .errors import WebError

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WORKSPACE = _REPO_ROOT / "var" / "workspace"
EXAMPLE_PATH = _REPO_ROOT / "examples" / "ai-agent-education.coursespec.yaml"

_ID_RE = re.compile(r"[^A-Za-z0-9\-]")


def workspace_dir() -> Path:
    configured = os.environ.get("COURSESPEC_WEB_WORKSPACE")
    path = Path(configured) if configured else DEFAULT_WORKSPACE
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_id(design_id: str) -> str:
    safe = _ID_RE.sub("", design_id or "")
    if not safe:
        raise WebError("설계서를 찾지 못했습니다. 다시 열어 주세요.", status=404)
    return safe


# --- 과정 초안 (M1) -----------------------------------------------------------

def draft_path(draft_id: str) -> Path:
    return workspace_dir() / f"{draft_id}.yaml"


def save_draft(draft: dict) -> None:
    path = draft_path(draft["id"])
    path.write_text(
        yaml.safe_dump(draft, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def load_draft(draft_id: str) -> dict:
    path = draft_path(draft_id)
    if not path.exists():
        raise WebError("해당 초안을 찾지 못했습니다. 목록에서 다시 열어 주세요.", status=404)
    try:
        data = yaml.safe_load(path.read_text("utf-8"))
    except yaml.YAMLError as exc:
        raise WebError("저장된 초안을 읽지 못했습니다. 새로 만들어 주세요.", status=500) from exc
    if not isinstance(data, dict):
        raise WebError("저장된 초안 형식이 올바르지 않습니다.", status=500)
    return data


# --- 설계서 (M2) --------------------------------------------------------------

def _roundtrip_yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def designs_dir() -> Path:
    path = workspace_dir() / "designs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def design_path(design_id: str) -> Path:
    return designs_dir() / f"{_safe_id(design_id)}.coursespec.yaml"


def save_design(design_id: str, data: dict) -> Path:
    """새 설계서를 작업 공간에 저장한다. 이후 수정은 반드시 검증된 패치로만 한다."""
    path = design_path(design_id)
    buf = io.StringIO()
    _roundtrip_yaml().dump(copy.deepcopy(data), buf)
    path.write_text(buf.getvalue(), encoding="utf-8")
    return path


def load_design(design_id: str) -> tuple[Path, dict]:
    path = design_path(design_id)
    if not path.exists():
        raise WebError("해당 설계서를 찾지 못했습니다. 과정 지도에서 다시 열어 주세요.", status=404)
    try:
        data = yaml.safe_load(path.read_text("utf-8"))
    except yaml.YAMLError as exc:
        raise WebError("저장된 설계서를 읽지 못했습니다. 다시 만들어 주세요.", status=500) from exc
    if not isinstance(data, dict):
        raise WebError("저장된 설계서 형식이 올바르지 않습니다.", status=500)
    return path, data


def copy_example_design(design_id: str) -> Path:
    """예시 설계서를 작업 공간에 복사해 연다 (원본 examples/ 는 절대 바꾸지 않는다)."""
    if not EXAMPLE_PATH.exists():
        raise WebError("예시 과정 파일을 찾지 못했습니다.", status=500)
    path = design_path(design_id)
    shutil.copyfile(EXAMPLE_PATH, path)
    return path


def requests_path(design_id: str) -> Path:
    return designs_dir() / f"{_safe_id(design_id)}.requests.json"


def load_requests(design_id: str) -> list[dict]:
    path = requests_path(design_id)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def save_requests(design_id: str, requests: list[dict]) -> None:
    path = requests_path(design_id)
    if requests:
        path.write_text(json.dumps(requests, ensure_ascii=False, indent=2), encoding="utf-8")
    elif path.exists():
        path.unlink()


def meta_path(design_id: str) -> Path:
    return designs_dir() / f"{_safe_id(design_id)}.meta.json"


def load_meta(design_id: str) -> dict:
    path = meta_path(design_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_meta(design_id: str, meta: dict) -> None:
    meta_path(design_id).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
