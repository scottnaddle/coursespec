"""CourseSpec 교수용 웹 UI 백엔드 (FastAPI).

범위: 실라버스 초안 생성·검토·인계 (M1), 과정 지도 확인·편집·수정 요청·확정 (M2).
설계서 수정은 검증된 JSON Patch 로만 하고, 확정은 상태 저장만 하며
plan/export/LMS 호출은 하지 않는다.
기본 화면에 YAML·JSON Patch·도구 이름을 보여 주지 않고, 교수가 보는 오류는 모두
한국어로 원인과 다음 행동을 담는다.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ..lint import lint
from ..patch import PatchError, patch_file
from .course_map import build_map, load_checked
from .design import generate_design, interpret_change_request, validate_design_payload
from .drafting import generate_draft
from .editing import apply_edits
from .errors import DraftError, WebError
from .extract import extract_sources
from .handoff import draft_to_syllabus
from .models import ChangeRequestBody, DraftUpdate, EditRequest
from .redact import redact
from .storage import (
    copy_example_design,
    load_design,
    load_draft,
    load_meta,
    load_requests,
    save_design,
    save_draft,
    save_meta,
    save_requests,
    workspace_dir,
)

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


def _file_hash(path: Path) -> str:
    """설계서 파일 내용의 지문. 수정 요청을 만든 뒤 파일이 바뀌었는지 확인하는 데 쓴다."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def create_app(
    generate: Callable[[str, str, list[tuple[str, str]]], dict] | None = None,
    design_generate: Callable[[dict], dict] | None = None,
) -> FastAPI:
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

        payload = (
            generate(title, goals, sources)
            if generate is not None
            else generate_draft(title, goals, sources)
        )

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
        payload = (
            generate(original_title, original_goals, sources)
            if generate is not None
            else generate_draft(original_title, original_goals, sources)
        )
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

    # --- M2: 과정 지도(설계서) -------------------------------------------------

    def _design_map(design_id: str) -> dict:
        path, data = load_design(design_id)
        confirmed = bool(load_meta(design_id).get("confirmed"))
        return build_map(design_id, data, path, confirmed=confirmed)

    def _unconfirm(design_id: str) -> None:
        """편집이나 수정 요청 적용에 성공하면 확정을 푼다(교수가 다시 검토·확정할 수 있게)."""
        meta = load_meta(design_id)
        if meta.get("confirmed"):
            meta["confirmed"] = False
            save_meta(design_id, meta)

    @app.post("/api/drafts/{draft_id}/design")
    def create_design(draft_id: str):
        draft = load_draft(draft_id)
        payload = (
            design_generate(draft)
            if design_generate is not None
            else generate_design(draft)
        )
        if not isinstance(payload, dict):
            raise WebError("만들어진 설계서를 읽지 못했습니다. 다시 시도해 주세요.", status=422)
        design_id = uuid4().hex
        payload["id"] = design_id
        # 스텁·주입·실모델 결과를 가리지 않고 저장 전 검증한다. 실패하면 파일은 남기지 않는다.
        validate_design_payload(payload)
        save_design(design_id, payload)
        return {"design_id": design_id, "map": _design_map(design_id)}

    @app.post("/api/designs/example")
    def open_example():
        design_id = f"example-{uuid4().hex[:8]}"
        copy_example_design(design_id)
        return {"design_id": design_id, "map": _design_map(design_id)}

    @app.get("/api/designs/{design_id}")
    def get_design(design_id: str):
        return _design_map(design_id)

    @app.post("/api/designs/{design_id}/edits")
    def edit_design(design_id: str, body: EditRequest):
        path, data = load_design(design_id)
        actions = [action.model_dump(exclude_unset=True) for action in body.actions]
        apply_edits(path, data, actions)
        _unconfirm(design_id)
        return _design_map(design_id)

    @app.post("/api/designs/{design_id}/change-requests")
    def create_change_request(design_id: str, body: ChangeRequestBody):
        path, data = load_design(design_id)
        ops, summary = interpret_change_request(body.text, data, path)
        request_id = uuid4().hex[:12]
        requests = load_requests(design_id)
        requests.append(
            {
                "request_id": request_id,
                "ops": ops,
                "summary": summary,
                "created_at": _now(),
                # 요청을 만든 시점의 설계서 내용 지문. 그 사이 바뀌면 적용을 막는다.
                "design_hash": _file_hash(path),
            }
        )
        save_requests(design_id, requests)
        return {"request_id": request_id, "summary": summary}

    def _pop_request(design_id: str, request_id: str) -> dict:
        requests = load_requests(design_id)
        for i, request in enumerate(requests):
            if request.get("request_id") == request_id:
                del requests[i]
                save_requests(design_id, requests)
                return request
        raise WebError("그 수정 요청을 찾지 못했습니다. 처음부터 다시 요청해 주세요.", status=404)

    @app.post("/api/designs/{design_id}/change-requests/{request_id}/apply")
    def apply_change_request(design_id: str, request_id: str):
        request = _pop_request(design_id, request_id)
        path, _ = load_design(design_id)
        # 요청을 만든 뒤 설계서가 바뀌었으면(삭제·추가가 엉뚱한 활동을 건드리는 것을 막기 위해) 적용하지 않는다.
        if request.get("design_hash") and request["design_hash"] != _file_hash(path):
            raise WebError(
                "설계서가 그 사이 바뀌어 이 변경을 적용하지 못했습니다. 수정 요청을 다시 본문에 적어 주세요.",
                status=409,
            )
        try:
            patch_file(path, request.get("ops") or [])
        except PatchError:
            raise WebError(
                "변경 내용을 적용하면 설계서에 문제가 생겨 적용하지 못했습니다. 수정 요청을 다시 본문에 적어 주세요.",
                status=409,
            ) from None
        _unconfirm(design_id)
        return _design_map(design_id)

    @app.post("/api/designs/{design_id}/change-requests/{request_id}/discard")
    def discard_change_request(design_id: str, request_id: str):
        _pop_request(design_id, request_id)
        return {"discarded": True}

    @app.post("/api/designs/{design_id}/confirm")
    def confirm_design(design_id: str):
        path, data = load_design(design_id)
        spec = load_checked(data, path)
        errors = [f for f in lint(spec) if f.is_error]
        if errors:
            raise WebError(
                "설계에 오류가 있어 아직 확정할 수 없습니다. 빨간 안내가 사라진 뒤 다시 눌러 주세요.",
                status=409,
            )
        meta = load_meta(design_id)
        meta["confirmed"] = True
        meta["confirmed_at"] = _now()
        save_meta(design_id, meta)
        return {"confirmed": True, "message": "설계가 확정되었습니다."}

    # 정적 프론트 빌드가 있으면 함께 서빙한다 (개발 시 Vite 프록시).
    dist = Path(__file__).resolve().parents[3] / "web" / "dist"
    if (dist / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")

    return app


app = create_app()
