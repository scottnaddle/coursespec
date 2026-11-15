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
    { "n": 1, "tool": "create_course",
      "args": { "fullname": "...", "numsections": 4, "visible": 0, "enablecompletion": 1 },
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

### 새 Moodle 강좌의 기본값

`plan --target moodle` 로 새 강좌를 만들 때 `create_course` 에는 `visible`(기본 `0`, 숨김)과
`enablecompletion`(기본 `1`, 완료 추적 켜짐)이 들어갑니다. CLI 에서는 `--visible 0|1`,
`--enable-completion/--no-enable-completion` 로 바꿉니다. 완료 추적을 끄면 활동 완료 조건이
동작하지 않는다는 경고가 계획에 포함됩니다.

배포 대상 moodle-agent-mcp 의 `create_course` 가 아직 `enablecompletion` 인자를 받지 않는 버전이면
실행기가 이 필드를 MCP 호출까지 전달하도록 갱신해야 합니다. 갱신 전 서버는 이 인자를 거부할 수
있으므로, 실행기는 계획의 `enablecompletion` 을 확인하고 MCP 버전을 함께 점검하세요.

Moodle 은 새 강좌에 기본 공지 포럼(예: `강좌공지`)을 자동으로 만듭니다. 이 포럼은 설계서에 없는
활동이며 계획은 수정·숨김·삭제하지 않는다는 `info` 변환을 남깁니다.

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
- **diff 계획**: 실행기가 읽기 도구로 조회해 넘긴 현재 LMS 상태와 설계서를 비교해 생성·수정·숨김 단계만 만듭니다. 퍼블리셔 자신은 네트워크를 호출하지 않으며, 삭제는 하지 않고 숨김으로 제안합니다.
- **제약**: 응시 기록이 있는 퀴즈의 문항은 Moodle이 바꾸지 못하게 합니다. 이런 경우는 loss로 보고하고 새 버전 퀴즈를 제안합니다.

## 차이 계획과 드리프트: `coursespec diff` (v0.3)

교수자가 LMS에서 직접 고친 내용은 원본과 어긋납니다. 양방향 동기화 대신, 배포 전에
"마지막 배포 이후 LMS에서 바뀐 활동"을 보여 주고 덮어쓸지 묻습니다. `diff` 도 네트워크를
호출하지 않습니다. 실행기가 읽어 온 스냅샷만 비교합니다.

```bash
coursespec diff course.yaml --target moodle --course-id 11 --start 2027-03-02 \
  --outline outline.json [--gradebook gradebook.json] [--record record.json] \
  [--accept-drift] [--json]
```

- `--outline`: moodle-agent-mcp `get_course_outline` 결과 JSON (`{"sections":[...]}`, 모듈의 `id`=cmid)
- `--gradebook`: 선택. `gradebook_overview` 의 `usergrades[0].gradeitems[]` (`cmid`, `idnumber`, ...).
  성적 항목의 `idnumber` 가 `cs:<설계서 id>:<활동 id>` 이면 outline 에 없어도 매칭에 씁니다.
- `--record`: 선택. 마지막 성공 배포 기록(아래 형식).
- 매칭 순서: `cs:` ID number → 기록의 cmid → 같은 섹션·modname·현재 이름(정확히 하나일 때만).
  후보가 여러 개면 추측하지 않고 unmatched 로 보고합니다.

동작은 **create · update · hide** 뿐입니다. 삭제 단계는 만들지 않습니다.

- **create**: 설계서에 있고 LMS 스냅샷에 없는 활동.
- **update**: 매칭된 활동의 이름 등이 설계서와 다를 때. 마지막 배포 기록과도 다르면 드리프트입니다.
- **hide**: `cs:` ID number 가 있거나 기록에 있는 이전 CourseSpec 활동이 설계서에서 빠졌을 때
  `set_activity_visibility(visible=false)`. 기본 공지 포럼과 확인되지 않은 LMS 활동은 건드리지 않고
  `info` 로만 알립니다.
- **drift**: LMS 값이 마지막 배포 기록과 다를 때. `--accept-drift` 가 없으면 해당 항목을 차단하고
  덮어쓰기/숨김 단계를 넣지 않으며 종료 코드는 `2` 입니다. 승인하면 단계를 넣고 차단을 풉니다.

JSON 출력에는 `summary`, `conversions`, `drifts`(`where`, `field`, `lms`, `last_deployed`, `spec`,
`blocked`), `steps`, `unmatched`, 그리고 apply 성공 뒤 실행기가 저장할 `record` 제안이 들어 있습니다.

### 배포 기록(record) 형식

배포 기록은 로컬 JSON 파일입니다. 실제 호스트 이름·토큰은 넣지 않습니다.

```json
{
  "spec_id": "ai-agent-education",
  "spec_version": "0.3.0",
  "target": "moodle",
  "course_id": 11,
  "start": "2027-03-02",
  "bound": {
    "course.id": 11,
    "w1-reading.cmid": 152,
    "w1-reading.instance": 33
  },
  "items": {
    "w1-reading": {"cmid": 152, "name": "읽기 자료 — …", "modname": "page", "idnumber": "cs:ai-agent-education:w1-reading"}
  }
}
```

apply 가 성공하면 실행기는 실제 cmid·이름·ID number 로 `bound`/`items` 를 갱신해 이 파일을 씁니다.
다음 `diff` 는 이 파일을 마지막 배포 기준으로 삼아 드리프트를 판단합니다.

## moodle-agent-mcp에 있으면 좋은 보강

v0.1 계획은 현재 MCP(도구 39개)로 그대로 실행되도록 만들었습니다. 다음이 추가되면 단계가 줄고 재배포가 쉬워집니다.

| 보강 | 효과 |
|---|---|
| `create_page`·`create_resource`·`create_assignment`·`create_quiz`·`create_forum`에 `settings` 인자 | ID number 기록용 `update_activity` 단계 5개 → 0개 |
| `create_course`에 `enablecompletion` | 완료 조건이 사이트 기본값에 의존하지 않음 (v0.3 계획은 이미 이 필드를 보냄) |
| ID number로 활동 조회 (예: `find_activity_by_idnumber`) | 재배포 매칭 |
| 피드백 문항 추가 도구 | `survey` 활동 내용까지 배포 |
| 강좌 단위 일괄 실행(트랜잭션 성격의 `apply_plan`) | 왕복 호출 감소, 실패 시 일관된 보고 |
