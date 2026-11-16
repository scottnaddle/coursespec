"""CourseSpec 교수용 웹 UI 백엔드 (FastAPI).

범위: 실라버스 초안 생성·검토·인계 (M1). LMS 실행·설계서 확정·배포는 하지 않는다.
기본 화면에 YAML·JSON Patch·도구 이름을 보여 주지 않고, 교수가 보는 오류는 모두
한국어로 원인과 다음 행동을 담는다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .drafting import generate_draft
from .errors import DraftError, WebError
from .extract import extract_sources
from .handoff import draft_to_syllabus
from .models import DraftUpdate
from .redact import redact
from .storage import load_draft, save_draft, workspace_dir

logger = logging.getLogger("coursespec.web")


class _RedactingFilter(logging.Filter):
    """로그 메시지의 비밀값 패턴을 감춘다."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(str(record.msg))
            if record.args:
                record.args = tuple(redact(str(a)) if isinstance(a, str) else a for a in record.args)
        except Exception:  # noqa: BLE001 - 적색이 로깅을 막으면 안 된다
            pass
        return True


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_filename(filename: str | None) -> str:
    if not filename:
        return "자료"
    return Path(filename).name or "자료"


def _normalize_suggestions(raw: list[dict]) -> list[dict]:
    out: list[dict] = []
    for i, item in enumerate(raw or []):
        out.append(
            {
                "id": str(item.get("id") or f"s{i + 1}"),
                "text": str(item.get("text") or ""),
                "target": str(item.get("target") or ""),
                "status": item.get("status", "pending"),
                "apply": item.get("apply") if isinstance(item.get("apply"), dict) else None,
            }
        )
    return out


def _public(draft: dict) -> dict:
    """화면·API 에 돌려주는 구조화 JSON. 내부 키(_로 시작)와 제안의 내부 규칙(apply)은
    빼고, 경로 비밀은 없다. 교수에게 YAML·JSON Patch·도구 이름을 보여 주지 않는다."""
    out = {key: value for key, value in draft.items() if not key.startswith("_")}
    if "suggestions" in out:
        out["suggestions"] = [
            {key: value for key, value in suggestion.items() if key != "apply"}
            for suggestion in out["suggestions"]
        ]
    return out


def _apply_suggestion(draft: dict, suggestion: dict) -> None:
    """수락한 제안을 본문에 반영한다. 제안은 수락 전에 본문을 바꾸지 않는다."""
    apply = suggestion.get("apply")
    if not isinstance(apply, dict):
        return
    kind = apply.get("kind")
    index = apply.get("index")
    value = apply.get("value")
    try:
        if kind == "week_title":
            draft["weeks"][index]["title"] = value
        elif kind == "grading_weight":
            draft["grading"][index]["weight"] = int(value)
    except (IndexError, KeyError, TypeError, ValueError):
        # 적용할 위치가 없으면 조용히 두고, 제안은 '수락' 상태로만 남긴다.
        pass


def create_app(generate: Callable[[str, str, list[tuple[str, str]]], dict] | None = None) -> FastAPI:
    app = FastAPI(title="CourseSpec 교수용 UI", docs_url=None, redoc_url=None, openapi_url=None)

    logging.getLogger().addFilter(_RedactingFilter())

    @app.exception_handler(WebError)
    async def _web_error_handler(request: Request, exc: WebError):
        return JSONResponse({"message": exc.message}, status_code=exc.status)

    @app.exception_handler(DraftError)
    async def _draft_error_handler(request: Request, exc: DraftError):
        logger.warning("초안 생성 실패: %s", exc.message)
        return JSONResponse({"message": exc.message}, status_code=503)

    @app.exception_handler(Exception)
    async def _unexpected_handler(request: Request, exc: Exception):
        logger.error("처리하지 못한 오류: %s: %s", type(exc).__name__, redact(str(exc)))
        return JSONResponse(
            {"message": "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요."},
            status_code=500,
        )

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/drafts")
    async def create_draft(
        title: str | None = Form(default=None),
        goals: str | None = Form(default=None),
        files: list[UploadFile] | None = File(default=None),
    ):
        if not title or not title.strip():
            raise WebError(
                "과목 이름을 입력해 주세요. 과목 이름만으로도 초안을 만들 수 있습니다.",
                status=422,
            )
        goals = (goals or "").strip()
        title = title.strip()

        uploads: list[tuple[str, bytes]] = []
        for upload in files or []:
            content = await upload.read()
            uploads.append((_clean_filename(upload.filename), content))

        sources, warnings = extract_sources(uploads)

        try:
            payload = (
                generate(title, goals, sources)
                if generate is not None
                else generate_draft(title, goals, sources)
            )
        except DraftError:
            raise

        draft = {
            "id": uuid4().hex,
            "title": (payload.get("title") or title).strip() or title,
            "intro": str(payload.get("intro") or ""),
            "goals": goals,
            "outcomes": [str(o) for o in (payload.get("outcomes") or [])],
            "weeks": [
                {"title": str(w.get("title") or ""), "summary": str(w.get("summary") or "")}
                for w in (payload.get("weeks") or [])
            ],
            "grading": [
                {"name": str(g.get("name") or ""), "weight": int(g.get("weight") or 0)}
                for g in (payload.get("grading") or [])
            ],
            "suggestions": _normalize_suggestions(payload.get("suggestions") or []),
            "sources_used": [_clean_filename(f) for f, _ in sources],
            "warnings": warnings,
            "created_at": _now(),
            "updated_at": _now(),
            "_sources": [{"filename": f, "text": text} for f, text in sources],
            "_input": {"title": title, "goals": goals},
        }
        save_draft(draft)
        return _public(draft)

    @app.get("/api/drafts/{draft_id}")
    def get_draft(draft_id: str):
        return _public(load_draft(draft_id))

    @app.patch("/api/drafts/{draft_id}")
    async def update_draft(draft_id: str, update: DraftUpdate):
        draft = load_draft(draft_id)
        data = update.model_dump(exclude_unset=True)
        for field in ("title", "intro", "outcomes", "weeks", "grading"):
            if field in data and data[field] is not None:
                draft[field] = data[field]
        draft["updated_at"] = _now()
        save_draft(draft)
        return _public(draft)

    @app.post("/api/drafts/{draft_id}/regenerate")
    async def regenerate(draft_id: str):
        draft = load_draft(draft_id)
        original_title = draft.get("_input", {}).get("title", draft["title"])
        original_goals = draft.get("_input", {}).get("goals", draft.get("goals", ""))
        sources = [(s["filename"], s["text"]) for s in draft.get("_sources", [])]
        try:
            payload = (
                generate(original_title, original_goals, sources)
                if generate is not None
                else generate_draft(original_title, original_goals, sources)
            )
        except DraftError:
            raise
        draft["title"] = (payload.get("title") or original_title).strip() or original_title
        draft["intro"] = str(payload.get("intro") or "")
        draft["outcomes"] = [str(o) for o in (payload.get("outcomes") or [])]
        draft["weeks"] = [
            {"title": str(w.get("title") or ""), "summary": str(w.get("summary") or "")}
            for w in (payload.get("weeks") or [])
        ]
        draft["grading"] = [
            {"name": str(g.get("name") or ""), "weight": int(g.get("weight") or 0)}
            for g in (payload.get("grading") or [])
        ]
        draft["suggestions"] = _normalize_suggestions(payload.get("suggestions") or [])
        draft["updated_at"] = _now()
        save_draft(draft)
        return _public(draft)

    def _set_suggestion_status(draft_id: str, sid: str, status: str, accept: bool):
        draft = load_draft(draft_id)
        suggestion: dict | None = None
        for item in draft.get("suggestions", []):
            if item.get("id") == sid:
                suggestion = item
                break
        if suggestion is None:
            raise WebError("해당 제안을 찾지 못했습니다.", status=404)
        suggestion["status"] = status
        if accept:
            _apply_suggestion(draft, suggestion)
        draft["updated_at"] = _now()
        save_draft(draft)
        return _public(draft)

    @app.post("/api/drafts/{draft_id}/suggestions/{sid}/accept")
    def accept_suggestion(draft_id: str, sid: str):
        return _set_suggestion_status(draft_id, sid, "accepted", accept=True)

    @app.post("/api/drafts/{draft_id}/suggestions/{sid}/skip")
    def skip_suggestion(draft_id: str, sid: str):
        return _set_suggestion_status(draft_id, sid, "skipped", accept=False)

    @app.post("/api/drafts/{draft_id}/handoff")
    def handoff(draft_id: str):
        draft = load_draft(draft_id)
        text = draft_to_syllabus(draft)
        # 인계 텍스트를 작업 공간에 저장해 두고, 설계서 생성·LMS 호출은 하지 않는다.
        (workspace_dir() / f"{draft_id}.handoff.md").write_text(text, encoding="utf-8")
        return {"text": text}

    # 정적 프론트 빌드가 있으면 함께 서빙한다 (개발 시 Vite 프록시).
    dist = Path(__file__).resolve().parents[3] / "web" / "dist"
    if (dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")

    return app


app = create_app()
