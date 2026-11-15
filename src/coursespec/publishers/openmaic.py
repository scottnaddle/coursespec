"""OpenMAIC 생성 계획: 설계서의 interactive_lecture 항목 → OpenMAIC 수업 생성 → 설계서에 기록.

LMS 배포 전, 설계 시점에 실행한다. 계획의 마지막 단계는 생성된 수업 id 와 스냅샷 경로를
설계서에 패치(coursespec patch)하는 것이어서, 이후 Moodle 배포는 같은 수업(lecture_id)을 쓴다.

OpenMAIC 서버 API (THU-MAIC/OpenMAIC, 2026-11 기준 코드에서 확인):
  POST /api/materials                 원본 바이트 업로드 (Content-Type, x-material-filename) → 201 {materialId}
  POST /api/generate-classroom        {requirement, materialIds?} → 202 {jobId, pollUrl}
  GET  /api/generate-classroom/{job}  → {status, done, result: {classroomId}}
  GET  /api/stages/{id}               수업 문서 전체 (stage + scenes + outline)
"""

from __future__ import annotations

from datetime import date
from typing import Any

from ..plan import Plan
from ..spec import Spec
from .moodle import ref

LEVEL_KO = {
    "remember": "기억", "understand": "이해", "apply": "적용",
    "analyze": "분석", "evaluate": "평가", "create": "창안",
}  # fmt: skip


def requirement(spec: Spec, item: dict[str, Any]) -> str:
    """교수자 프롬프트에 과정 맥락(단원·학습목표·분량)을 덧붙인 생성 요구사항."""
    lec = item.get("lecture", {})
    unit = spec.units[spec.unit_index[spec.unit_of[item["id"]]]]
    outcomes = {o["id"]: o for o in spec.outcomes}
    lines = [lec.get("prompt", "").strip() or item["title"], "", "[과정 맥락]",
             f"- 과정: {spec.title}", f"- 단원: {unit['title']}", f"- 수업 제목: {item['title']}"]  # fmt: skip
    linked = [outcomes[o] for o in item.get("outcomes", []) if o in outcomes]
    if linked:
        lines.append("- 이 수업이 다룰 학습목표:")
        for o in linked:
            level = f" ({LEVEL_KO[o['level']]} 수준)" if o.get("level") else ""
            lines.append(f"  - {o['statement']}{level}")
    if item.get("estimated_minutes"):
        lines.append(f"- 분량: 약 {item['estimated_minutes']}분")
    if spec.data.get("language"):
        lines.append(f"- 언어: {spec.data['language']}")
    if lec.get("materials"):
        lines.append("- 첨부 자료를 근거로 내용을 구성하고, 자료에 없는 사실은 단정하지 마세요.")
    return "\n".join(lines)


def plan_openmaic(
    spec: Spec,
    start: date | None = None,
    server: str | None = None,
    regenerate: bool = False,
    archive_dir: str = "lectures",
) -> Plan:
    plan = Plan("openmaic", spec.id, spec.data.get("version"), start.isoformat() if start else "-")
    uploaded: set[str] = set()
    for _, _, item in spec.iter_items():
        if item["type"] != "interactive_lecture":
            continue
        iid = item["id"]
        lec = item.get("lecture", {})
        if lec.get("classroom") and not regenerate:
            plan.note(iid, "info", f"이미 생성된 수업({lec['classroom']['id']})이 있어 건너뜁니다 (--regenerate 로 다시 생성).")
            continue

        material_refs = []
        for mid in lec.get("materials", []):
            m = spec.materials.get(mid)
            if m is None:
                continue
            if mid not in uploaded:
                plan.add("openmaic_upload_material",
                         {"source": m["source"], "filename": m["source"].rsplit("/", 1)[-1], "title": m["title"],
                          "sha256": m.get("sha256")},
                         f"자료 업로드: {m['title']}", binds={f"mat.{mid}": "materialId"}, verify=True)  # fmt: skip
                uploaded.add(mid)
                if not m.get("rights", {}).get("license"):
                    plan.note(mid, "warn", "이용 권리가 확인되지 않은 자료가 OpenMAIC 서버로 올라갑니다.")
            material_refs.append(ref(f"mat.{mid}"))
        if material_refs:
            plan.note(iid, "info", "업로드한 자료의 내용 추출이 끝난 뒤 생성이 시작되도록 실행기가 확인해야 합니다.")

        body: dict[str, Any] = {"requirement": requirement(spec, item)}
        if material_refs:
            body["materialIds"] = material_refs
        plan.add("openmaic_request", {"method": "POST", "path": "/api/generate-classroom", "json": body},
                 f"수업 생성 요청: {item['title']}", binds={f"{iid}.job": "jobId"})  # fmt: skip
        plan.add("openmaic_wait_job", {"job_id": ref(f"{iid}.job")},
                 f"생성 완료 대기: {iid}", binds={f"{iid}.classroom": "result.classroomId"})  # fmt: skip

        archive = f"{archive_dir}/{iid}.stage.json"
        plan.add("openmaic_request",
                 {"method": "GET", "path": f"/api/stages/{ref(iid + '.classroom')}", "save_to": archive},
                 f"수업 문서 스냅샷 저장: {archive}")  # fmt: skip

        record: dict[str, Any] = {"id": ref(f"{iid}.classroom"), "archive": archive}
        if server:
            record["server"] = server
        plan.add("coursespec_patch",
                 {"ops": [{"op": "add", "path": f"{spec.pointer[iid]}/lecture/classroom", "value": record}]},
                 f"설계서에 수업 기록: {iid}")  # fmt: skip

    if not plan.steps and not plan.conversions:
        plan.note("course", "info", "생성할 인터랙티브 강의가 없습니다.")
    plan.note("course", "info", "HTML·동영상 내보내기는 OpenMAIC 화면에서 하고 경로를 lecture.exports 에 기록하세요 (Canvas 대체 경로).")
    return plan
