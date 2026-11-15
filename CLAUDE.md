# 이 저장소에서 일하는 에이전트를 위한 안내

- 스키마의 원본은 `schema/coursespec.schema.json` 하나입니다. 필드를 바꾸면 `docs/spec-guide.md`, 예시, 테스트를 함께 고치세요.
- 퍼블리셔는 **네트워크를 호출하지 않습니다.** 계획(Plan)만 만듭니다. 실행은 이 저장소 밖(허브·에이전트)의 일입니다.
- LMS에 대응이 없는 기능은 조용히 버리지 말고 `plan.note(where, "warn"|"loss", 메시지)`로 보고하세요. 메시지는 교수자가 읽는 한국어입니다.
- Moodle 단계의 도구 이름·인자는 moodle-agent-mcp의 실제 시그니처와 일치해야 합니다. 새 인자를 쓰기 전에 그 저장소의 `src/moodle_mcp/server.py`를 확인하세요.
- Canvas 호출 형식이 공식 문서로 확인되지 않았으면 `verify=True`를 붙이세요.
- 설계서·예시·테스트 픽스처에 실제 학생 정보, 토큰, 실서버 주소를 넣지 마세요.
- 설계서 수정은 파일을 직접 다시 쓰지 말고 `coursespec patch`(검증된 JSON Patch)로 하세요. 주석이 보존되고 검증 실패 시 기록되지 않습니다.
- 세 프로젝트(CourseSpec·OpenMAIC·DeepTutor)는 서로 직접 부르지 않습니다. 공유 계약은 `docs/integration.md` 에 있습니다.
- OpenMAIC API 형식을 바꾸기 전에 THU-MAIC/OpenMAIC 의 `app/api/` 코드를 확인하세요.
- IMS Common Cartridge XSD 는 `schema/imscc/` 의 공식 1EdTech 파일을 그대로 씁니다. 수정하지 말고, 바꿔야 하면 `schema/imscc/NOTICE.md` 와 출처를 먼저 확인하세요.
- `coursespec export`/`verify` 도 네트워크를 호출하지 않습니다. XSD 는 로컬 resolver 로만 읽고(`no_network=True`), 비표준 Canvas/Moodle 확장을 만들지 않습니다.
- CC 에 없는 기능은 `ExportResult.conversions` 에 `info`/`warn`/`loss` 로 남기세요. 조용히 버리지 않습니다.
- 과정 설계 스킬은 `skills/design-agent/SKILL.md` 입니다. 초안은 lint 루프로 다듬고, 저장 후 수정은 반드시 `coursespec patch` 로만 합니다.
- 확인: `pytest -q` 와 `coursespec lint examples/ai-agent-education.coursespec.yaml examples/design-agent-demo/course.coursespec.yaml`.
