# CourseSpec · OpenMAIC · DeepTutor 연동

세 프로젝트는 서로를 직접 부르지 않습니다. **CourseSpec이 정의한 공유 열쇠와 Moodle을 통해서만** 만납니다. 셋 다 빠르게 바뀌는 오픈소스라서, 직접 결합하면 하나가 업데이트될 때마다 나머지가 흔들리기 때문입니다.

| 구성 | 맡는 일 | 시점 |
|---|---|---|
| **CourseSpec** | 과정 구조·학습목표·자료의 원본, 공유 열쇠 정의, 배포 계획 | 설계·배포·개정 |
| **OpenMAIC** | 몰입형 수업(슬라이드·내레이션·퀴즈·시뮬레이션) 생성과 재생 | 설계(생성), 운영(재생) |
| **DeepTutor** | 학습자 튜터 | 운영 |
| **Moodle** | 학습자 신원·성적부·이수. 학생 데이터의 유일한 원본 | 운영 |
| **UBIONAI 허브** | 테넌트별 키와 가명처리를 거치는 LLM 관문 | 전 구간 |

## 세 가지 공유 계약

### 1. 식별자: `cs:<설계서 id>:<활동 id>`

- Moodle 활동의 ID number에 기록됩니다 (v0.1부터).
- OpenMAIC 수업은 `lecture.classroom.id`로 설계서 활동에 묶입니다 (v0.2).
- 튜터 팩의 모든 활동·문항은 이 열쇠(`…#q2` 형태의 문항 번호 포함)로 표기됩니다.

그래서 "Moodle cmid 1234 = 설계서 w4-lecture = OpenMAIC 수업 stg_42"가 언제든 추적되고, 운영 데이터가 설계의 의미(학습목표)로 번역됩니다.

### 2. 학습목표 어휘: `outcomes[].id`

활동, 문항, 자료가 모두 같은 학습목표 id를 참조합니다. 튜터는 "퀴즈 2번 오답"을 "lo1 약점"으로 해석하고, OpenMAIC 생성 요구사항에는 해당 학습목표 문장이 자동으로 들어가며, 린트는 목표마다 다루는 활동·평가·튜터 자료가 있는지 봅니다.

### 3. 자료 매니페스트: `materials[]`

교수자 자료를 단원·학습목표와 연결하고 용도를 밝힙니다.

| `uses` | 의미 | 쓰는 곳 |
|---|---|---|
| `generation` | 콘텐츠 생성 입력 | OpenMAIC 수업 생성 (`lecture.materials`) |
| `tutor` | 튜터 지식베이스 | 튜터 팩 → DeepTutor 지식베이스 |
| `learner` | 학습자에게 배포 가능 | `file` 활동의 `material` |

같은 자료가 수업 생성과 튜터 지식베이스에 함께 쓰여야 튜터 설명이 수업 내용과 어긋나지 않습니다. 권리(`rights.license`)가 확인되지 않은 자료는 경고(W112)이고, `learner` 허용이 없는 자료를 학습자에게 배포하려 하면 오류(E017)입니다.

## 흐름

### 설계 — 수업 생성 (`plan --target openmaic`)

```
coursespec plan course.yaml --target openmaic --server ubion-maic --json
```

| 단계 | 도구 | 하는 일 |
|---|---|---|
| 1 | `openmaic_upload_material` | `lecture.materials` 의 자료 업로드 (`POST /api/materials`, 원본 바이트 + `x-material-filename`) → `materialId` |
| 2 | `openmaic_request` | `POST /api/generate-classroom` `{requirement, materialIds}` → `jobId` |
| 3 | `openmaic_wait_job` | `GET /api/generate-classroom/{jobId}` 를 `done` 까지 폴링 → `result.classroomId` |
| 4 | `openmaic_request` | `GET /api/stages/{classroomId}` 수업 문서 전체를 `save_to` 경로에 저장 (워크스페이스에서 버전 관리) |
| 5 | `coursespec_patch` | 설계서의 `lecture.classroom` 에 id·스냅샷 경로 기록 (검증된 JSON Patch) |

생성 요구사항(`requirement`)은 교수자 프롬프트에 과정명·단원·학습목표(블룸 수준 포함)·분량·언어와 "자료에 근거하라"는 지시를 덧붙여 만듭니다. 이미 수업이 기록된 항목은 건너뜁니다 (`--regenerate` 로 다시 생성).

교수자는 OpenMAIC 워크벤치에서 수업을 다듬은 뒤, Canvas 같은 LMS를 위해 HTML·동영상으로 내보내고 그 경로를 `lecture.exports` 에 기록합니다 (현재는 수동).

### 배포

| 대상 | 인터랙티브 강의 |
|---|---|
| Moodle | `create_openmaic` 에 `lecture_id` 로 기록된 수업 연결. 수업이 없으면 요구사항을 `prompt` 로 넘기되 경고 (자료가 전달되지 않음) |
| Canvas | `exports.html` → 없으면 `exports.video` 를 파일로 업로드해 모듈 아이템으로. 실시간 상호작용·AI 채점 손실을 경고. 둘 다 없으면 배포 제외(loss) |
| 튜터 | `coursespec tutor-pack course.yaml --start 2027-03-02 --out tutor/` → `tutor-pack.json` + `SKILL.md` |

### 운영

학습자는 Moodle 안에서 OpenMAIC 수업을 듣고, 막히면 튜터를 엽니다. 튜터는 Moodle에서 **그 학습자 본인의 기록만** 받아 튜터 팩의 `mapping` 으로 학습목표에 연결합니다. 이 단계의 전제 조건은 학습자 단위 권한 체계입니다. moodle-agent-mcp의 서비스 계정 토큰(교수자 권한)으로는 이 경로를 열면 안 됩니다.

튜터 팩의 `integrity` 규칙은 설계에서 내려옵니다. 채점 활동이 열려 있는 기간(공개일 ~ 최종 마감, 동료평가는 평가 마감까지)에는 `hint_only`(정답·대필 없이 힌트만), 채점 토론은 `no_ghostwriting`(게시글 대필 금지)입니다. 학업 정직성을 튜터 프롬프트 작성자의 기억에 맡기지 않고, 설계서의 날짜와 채점 정보에서 자동으로 만듭니다.

### 개정

Moodle의 운영 결과는 **가명 집계**로만 워크스페이스에 돌아옵니다 (로드맵). 이벤트는 xAPI 같은 표준 형식에 `cs:` 식별자를 실어 보내는 것을 권합니다. 설계 에이전트는 "lo3 문항 정답률 저조", "w4-lecture 이탈 구간" 같은 신호를 받아 다음 학기 설계서 수정안을 JSON Patch로 제안합니다.

## 허브를 LLM 관문으로

OpenMAIC는 OpenAI 호환 API를, DeepTutor는 여러 LLM 공급자를 지원하므로, 두 시스템의 LLM 엔드포인트를 UBIONAI 허브의 `/t/<site>/v1/chat/completions` 로 돌리면 테넌트별 키 관리와 한국어 가명처리가 세 시스템 전체에 일괄 적용됩니다. 각 오픈소스를 고치지 않아도 됩니다. 다만 두 가지를 먼저 보강·검증해야 합니다.

- 가명처리기는 Moodle 응답 구조에 맞춰져 있습니다. 학습자의 자유 대화문에서의 동작을 따로 시험해야 합니다.
- 허브 프록시는 스트리밍을 끄고 있습니다. OpenMAIC 실시간 강의와 튜터 대화에는 스트리밍이 필요합니다.

## 추진 순서

1. **CourseSpec ↔ OpenMAIC** (v0.2, 이 문서): 교수자 쪽, 학생 데이터 거의 없음, mod_openmaic 이미 있음.
2. **운영 결과 피드백 루프**: 가명 집계, xAPI, 개정 제안.
3. **DeepTutor**: 학습자 권한 체계와 허브 스트리밍이 준비된 뒤. 튜터 팩 형식은 미리 정의해 두었습니다.

## 확인된 것과 아닌 것

- OpenMAIC API 경로와 본문은 THU-MAIC/OpenMAIC 저장소 코드(2026-11)에서 확인했습니다. 자료 업로드 단계는 실제 서버에서 검증 전이라 `verify` 로 표시됩니다. 업로드한 자료의 추출이 끝나기 전에 생성을 시작하면 자료가 반영되지 않을 수 있어, 실행기가 추출 상태를 확인해야 합니다.
- mod_openmaic 의 `lecture_id` 가 OpenMAIC `classroomId` 와 같은 값을 받는지, 같은 서버를 바라보는지는 플러그인 쪽에서 확인이 필요합니다.
- 튜터 팩의 `SKILL.md` 는 일반 에이전트 스킬 형식입니다. DeepTutor 의 스킬 로딩 방식에 맞춰 최종 조정이 필요할 수 있습니다.
