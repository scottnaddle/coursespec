# 배포 프로토콜: plan → 승인 → apply

## 계획(Plan) 형식

`coursespec plan ... --json`의 출력입니다.

```json
{
  "target": "moodle",
  "spec": { "id": "ai-agent-education", "version": "0.1.0" },
  "start": "2027-03-02",
  "summary": { "steps": 30, "conversions": { "info": 2, "warn": 3, "loss": 0 } },
  "conversions": [ { "where": "w4-lecture", "severity": "warn", "message": "..." } ],
  "steps": [
    { "n": 1, "tool": "create_course", "args": { "fullname": "...", "numsections": 4 },
      "about": "강좌 생성", "binds": { "course.id": "courseid" } },
    { "n": 8, "tool": "create_quiz", "args": { "course_id": "${course.id}", "section": 1 },
      "binds": { "w1-quiz.cmid": "cmid", "w1-quiz.instance": "instance" } },
    { "n": 10, "tool": "add_quiz_questions", "args": { "quiz_id": "${w1-quiz.instance}", "questions": [] } }
  ]
}
```

- `tool`: Moodle은 moodle-agent-mcp 도구 이름, Canvas는 `canvas_request`(method·path·json) 또는 `canvas_upload_file`, OpenMAIC은 `openmaic_upload_material`·`openmaic_request`(method·path·json·`save_to`)·`openmaic_wait_job`, 그리고 공통으로 `coursespec_patch`(ops).
- `binds`: 이 단계 결과에서 꺼낼 값. `"이름": "결과 경로"`이며 경로는 점으로 구분합니다 (`sections.0.section`).
- `${이름}`: 앞 단계에서 bind된 값. 문자열 전체가 참조면 원래 타입(int)으로, 경로 속에 섞이면 문자열로 바뀝니다.
- `{"$file": "경로"}`: 실행기가 워크스페이스 파일을 읽어 base64로 넣을 자리.
- `verify: true`: 호출 형식을 실제 LMS에서 아직 검증하지 않은 단계.

계획의 Moodle 단계에는 `confirm` 인자가 없습니다. 아래 절차대로 실행기가 붙입니다.

`coursespec_patch` 단계는 실행기가 참조를 푼 연산을 `coursespec.patch.patch_file(설계서, ops)` 로 적용합니다. 검증을 통과하지 못하면 예외가 나고 설계서는 바뀌지 않습니다. OpenMAIC 생성 결과가 설계서에 기록되는 경로가 이것입니다.

## 파일 내보내기: export → verify

MCP 없이 LMS 가져오기 파일이 필요하면 `export` 를 씁니다. 계획(plan)과 마찬가지로 네트워크를 호출하지 않습니다.

```bash
coursespec export course.yaml --format imscc --out course.imscc
coursespec verify course.imscc
```

- `export` 는 먼저 설계서 스키마와 린트를 검사합니다. 린트 오류가 있으면 `--force` 없이는 중단합니다.
- ZIP 루트에 `imsmanifest.xml` 을 두고, 단원을 모듈 item 으로, 활동을 리소스 item 으로 씁니다.
- 표준 CC 1.3 에 없는 기능은 `info`/`warn`/`loss` 변환 보고서로 알리고, 비표준 XML 을 임의로 만들지 않습니다.
- 쓰기가 끝나면 `verify` 와 같은 검증을 자동 실행합니다. 검증 오류가 없어야 종료 코드가 0 입니다(경고는 허용).
- `verify` 는 공식 1EdTech XSD(`schema/imscc/`)와 ZIP 참조를 로컬에서 검사합니다. 실제 LMS 가져오기 검증은 별도 단계입니다.

## 실행기(executor)의 책임

실행기는 허브나 에이전트가 맡습니다. 이 저장소는 참조 해석 도우미 `coursespec.plan.resolve` · `collect`만 제공합니다.

1. **미리보기**: 계획의 `summary`, `conversions` 전체, 단계 목록을 교수자에게 보여 줍니다. loss가 있으면 반드시 눈에 띄게.
2. **승인**: 교수자가 계획 *전체*를 승인합니다. 단계마다 묻지 않습니다.
3. **실행**: 단계를 순서대로 `resolve(args, bound)` → 호출(Moodle은 `confirm=true`) → `collect(step, result, bound)`.
4. **중단 규칙**: 오류가 나면 즉시 멈추고, 그때까지 만들어진 것(`bound`)과 실패 단계를 보고합니다. 자동 롤백은 하지 않습니다. 이미 만들어진 활동은 ID number로 다음 실행 때 찾을 수 있습니다.
5. **기록**: 실행 결과(설계서 id·version, 대상, 시작일, bound 전체)를 배포 기록으로 남깁니다. 재배포와 드리프트 감지의 근거입니다.

```python
from coursespec.plan import resolve, collect

bound = {}
for step in plan.steps:
    args = resolve(step.args, bound)
    result = call_mcp(step.tool, {**args, "confirm": True})   # Moodle
    if "error" in result:
        raise PublishError(step, result, bound)
    collect(step, result, bound)
```

## 재배포 (로드맵 v0.2)

첫 배포는 쉽고, 어려운 것은 "3주차 퀴즈를 고친 뒤 다시 배포"입니다. 새로 만들지 않고 기존 활동을 찾아 고쳐야 합니다.

- **매칭 열쇠**: Moodle 활동의 ID number에 `cs:<설계서 id>:<활동 id>`를 심습니다 (v0.1에서 이미 기록). Moodle 백업·복원 후에도 남습니다.
- **diff 계획**: 퍼블리셔가 현재 LMS 상태(읽기 도구로 조회)와 설계서를 비교해 생성·수정·숨김 단계만 만듭니다. 삭제는 하지 않고 숨김으로 제안합니다.
- **제약**: 응시 기록이 있는 퀴즈의 문항은 Moodle이 바꾸지 못하게 합니다. 이런 경우는 loss로 보고하고 새 버전 퀴즈를 제안합니다.

## 드리프트 감지 (로드맵 v0.3)

교수자가 LMS에서 직접 고친 내용은 원본과 어긋납니다. v0.x는 양방향 동기화 대신, 배포 전에 "마지막 배포 이후 LMS에서 바뀐 활동"을 보여 주고 덮어쓸지 묻습니다.

## moodle-agent-mcp에 있으면 좋은 보강

v0.1 계획은 현재 MCP(도구 39개)로 그대로 실행되도록 만들었습니다. 다음이 추가되면 단계가 줄고 재배포가 쉬워집니다.

| 보강 | 효과 |
|---|---|
| `create_page`·`create_resource`·`create_assignment`·`create_quiz`·`create_forum`에 `settings` 인자 | ID number 기록용 `update_activity` 단계 5개 → 0개 |
| `create_course`에 `enablecompletion` | 완료 조건이 사이트 기본값에 의존하지 않음 |
| ID number로 활동 조회 (예: `find_activity_by_idnumber`) | 재배포 매칭 |
| 피드백 문항 추가 도구 | `survey` 활동 내용까지 배포 |
| 강좌 단위 일괄 실행(트랜잭션 성격의 `apply_plan`) | 왕복 호출 감소, 실패 시 일관된 보고 |
