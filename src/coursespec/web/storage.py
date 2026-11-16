"""서버 쪽 작업 공간에 과정 초안을 YAML 로 저장·조회한다.

API·화면은 구조화된 JSON 만 주고받고, 저장 형식만 YAML 이다. 교수 화면에 YAML 은
보여 주지 않는다. 작업 공간 경로는 환경변수 `COURSESPEC_WEB_WORKSPACE`(없으면 저장소
로컬 `var/workspace`, gitignore)를 쓴다.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

from .errors import WebError

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_WORKSPACE = _REPO_ROOT / "var" / "workspace"


def workspace_dir() -> Path:
    configured = os.environ.get("COURSESPEC_WEB_WORKSPACE")
    path = Path(configured) if configured else DEFAULT_WORKSPACE
    path.mkdir(parents=True, exist_ok=True)
    return path


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
