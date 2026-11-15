# LMS 매핑

퍼블리셔가 설계서를 각 LMS로 옮기는 규칙입니다. 손실이나 변환이 생기면 계획의 **변환 보고서**에 `info`(참고) · `warn`(동작이 달라짐) · `loss`(배포되지 않거나 기능 손실)로 남습니다.

v0.2부터 세 번째 대상 `openmaic` 이 있습니다. LMS가 아니라 설계 시점의 수업 생성 대상이며, 단계는 [integration.md](integration.md)에 있습니다.

검증 상태 — Moodle: moodle-agent-mcp 도구 시그니처와 `local_ubionai` 코드 기준. Canvas: Canvas REST API v1 / New Quizzes API 문서 지식 기준 **초안**이며, 계획에서 `verify` 로 표시된 단계(New Quizzes, 루브릭)는 실제 인스턴스에서 형식을 확인해야 합니다.

## IMS Common Cartridge 1.3 (파일 내보내기)

`coursespec export --format imscc` 는 MCP 없이 LMS 가져오기 파일을 만드는 경로입니다.
ZIP 루트의 `imsmanifest.xml`, organization `rooted-hierarchy`, 상위 `LearningModules` item(제목 없음) 아래에
단원 item 과 활동 item 을 둡니다. `coursespec verify` 가 공식 1EdTech XSD 로 로컬 검증합니다.

| CourseSpec | CC 1.3 리소스 | 비고 |
|---|---|---|
| 과정·단원 | organization + item | 단원 item 에 `title` 필요 |
| `page` | `webcontent` (HTML5) | `video_url` 은 링크로 넣고 info |
| `file` | `webcontent` 파일 복사 | `material.uses` 에 `learner` 가 없으면 loss, 파일이 없으면 warn |
| `assignment` | `assignment_xmlv1p0` | `title`·`instructor_text`·`gradable`·`submission_formats` |
| `quiz` | QTI 1.2.1 CC 프로필 | 문항별 `cc_profile`: multiple_choice·multiple_response·true_false·fib·essay |
| `discussion` | `imsdt_xmlv1p3` | Q&A 형식은 info |
| `peer_review` | `assignment_xmlv1p0` | 평가 점수·평가 마감은 CC 에 없어 loss |
| `wiki` `glossary` | `webcontent` | 학생 편집·용어집 기능 손실 warn |
| `survey` `h5p` | — | loss, 내보내지 않음 |
| `interactive_lecture` | `webcontent` (HTML/동영상) | `lecture.exports` 가 있을 때만, 상호작용 손실 warn. 없으면 loss |
| 배지·완료 조건·선수조건·성적 가중치 | — | CC 1.3 표준에 없어 info/warn, 비표준 XML 을 만들지 않음 |
| 공개일·마감일 | — | 날짜 요소 대신 본문 힌트(info)만 |

Canvas 전용 파일(`course_settings/canvas_export.txt` 등)은 만들지 않습니다. Moodle·Canvas 공용 패키지입니다.

## 구조

| CourseSpec | Moodle | Canvas |
|---|---|---|
| 과정 | 강좌 (`create_course`, topics 형식) | 강좌 (`POST /accounts/:id/courses`, 기본 화면 modules) |
| 단원 `units[]` | 섹션 (`update_section` / 기존 강좌는 `add_sections`) | 모듈 (`POST /courses/:id/modules`) |
| 단원 `summary` | 섹션 요약 | — (info: 배포 안 됨) |
| 단원 `opens_day` | 섹션 접근 제한 open_from | 모듈 `unlock_at` |
| 활동 | 활동 (cmid) | 콘텐츠 + 모듈 아이템 |
| 활동 id | ID number `cs:<설계서>:<활동>` | (로드맵) 재배포 매칭용 저장소 필요 |
| 성적 카테고리 | 성적 카테고리 (`set_grade_categories`) | 과제 그룹 `group_weight` + 가중치 적용 |
| 집계 `mean` | 카테고리 평균 | warn: 점수 합산으로 계산 |
| 배지 | 강좌 배지 (비활성으로 생성) | loss: 코어에 없음 (Canvas Credentials 별도) |

## 활동 유형

| CourseSpec | Moodle 도구 | Canvas | 비고 |
|---|---|---|---|
| `page` | `create_page` | 페이지 + Page 아이템 | Canvas: 동영상은 링크로 (info) |
| `file` | `create_resource` | 3단계 업로드 + File 아이템 | `material` 이면 자료 매니페스트의 source. 로컬 경로는 실행기가 읽어 전달 |
| `assignment` | `create_assignment` | 과제 + Assignment 아이템 | Canvas: 파일 수 제한 없음 (info) |
| `quiz` | `create_quiz` + `add_quiz_questions` | New Quiz + 문항 + Assignment 아이템 | 문항 변환은 아래 |
| `discussion` | `create_forum` | 토론 (채점 시 assignment 포함) | qanda → `require_initial_post` |
| `peer_review` | `create_workshop` | 동료 검토 켠 과제 | Canvas: 평가 점수 loss, 평가 마감 warn |
| `wiki` | `create_wiki` | 학생 편집 가능 페이지 | Canvas: warn |
| `glossary` | `create_glossary` | 토론 | Canvas: warn |
| `survey` | `create_feedback` | — | Moodle: 문항 추가 불가 warn / Canvas: loss |
| `h5p` | `create_h5pactivity` | — | Canvas: loss (LTI 필요) |
| `interactive_lecture` | `create_openmaic` (`lecture_id` 또는 `prompt`) | 내보낸 HTML(우선)·동영상 파일 + File 아이템 | Moodle: mod_openmaic 필요, 미생성 수업 warn / Canvas: 내보내기 있으면 warn(상호작용 손실), 없으면 loss |

## 완료 조건

| `completion.mode` | Moodle | Canvas `completion_requirement` |
|---|---|---|
| none | — | — |
| manual | manual | `must_mark_done` |
| view | view | `must_view` |
| submit | submit (워크숍은 warn → grade) | `must_submit` |
| grade | grade | warn → `must_submit` |
| pass | pass + gradepass | `min_score` |
| posts | posts(N) | `must_contribute` (N>1 이면 warn) |

Moodle은 생성 도구가 받는 완료 인자(`completion_view`, `completion_submit`, `completion_pass_grade`, `completion_posts` 등)를 먼저 쓰고, 나머지는 `set_completion`으로 설정합니다. 강좌의 이수 추적이 켜져 있어야 합니다.

## 선수조건과 공개일

| CourseSpec | Moodle | Canvas |
|---|---|---|
| 활동 `requires` (다른 단원) | 활동 접근 제한 (완료 조건) | warn: 그 단원 **모듈 전체**가 선수조건으로 넓어짐 |
| 활동 `requires` (같은 단원) | 활동 접근 제한 | warn: 모듈 `require_sequential_progress` |
| 단원 `requires` | 섹션 접근 제한 | warn: 모듈 선수조건으로 넓어짐 |
| 활동 `opens_day` | 활동 접근 제한 open_from (+퀴즈 timeopen, 과제 제출 시작) | 과제·퀴즈·토론 `unlock_at` / 페이지·파일은 warn |
| `due_day` | 퀴즈 timeclose, 과제·포럼 duedate, 워크숍 제출 마감 | `due_at` |
| `cutoff_day` | 과제 cutoffdate | `lock_at` |

Canvas 선수조건은 선행 모듈의 완료 요건이 모두 충족돼야 풀립니다. 선행 활동에 완료 조건이 없으면 warn을 남깁니다.

## 문항

| CourseSpec | Moodle | Canvas New Quizzes |
|---|---|---|
| multichoice (단일 정답) | multichoice single, 정답 fraction 1 | `choice` / Equivalence |
| multichoice (`multiple`) | multichoice, 정답마다 1/n | `multi-answer` / AllOrNothing (warn: 부분 점수 없음) |
| truefalse | truefalse | `true-false` |
| shortanswer | shortanswer, 인정 답안마다 fraction 1 | loss: `essay`(수동 채점)로 변환 |
| essay | essay + graderinfo | `essay` |
| 보기별 feedback | 답안 feedback | info: 배포 안 됨 |

## 새 LMS 추가하기

1. `src/coursespec/publishers/<lms>.py`에 `plan_<lms>(spec, start, ...) -> Plan`을 만듭니다.
2. 위 표에 열을 추가하고, 대응이 없는 기능은 `plan.note(where, "loss", ...)`로 숨김없이 보고합니다.
3. `publishers/__init__.py`의 `TARGETS`에 등록하고, 예시 설계서로 "모든 참조가 풀린다"는 테스트를 추가합니다 (`tests/test_canvas.py` 참고).

IMS Common Cartridge 1.3 파일 내보내기는 v0.2.1에서 완료했습니다(위 절 참고). 남은 후보: COURSEMOS LXP.
