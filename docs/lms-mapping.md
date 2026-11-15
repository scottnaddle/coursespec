# LMS 매핑

퍼블리셔가 설계서를 각 LMS로 옮기는 규칙입니다. 손실이나 변환이 생기면 계획의 **변환 보고서**에 `info`(참고) · `warn`(동작이 달라짐) · `loss`(배포되지 않거나 기능 손실)로 남습니다.

v0.2부터 세 번째 대상 `openmaic` 이 있습니다. LMS가 아니라 설계 시점의 수업 생성 대상이며, 단계는 [integration.md](integration.md)에 있습니다.

검증 상태 — Moodle: moodle-agent-mcp 도구 시그니처와 `local_ubionai` 코드 기준. Canvas: Canvas REST API v1 / New Quizzes API 문서 지식 기준이며, 로컬 Canvas 테스트 인스턴스에서 IMSCC 가져오기와 계획의 `verify=True` 단계를 실행했습니다. 가져오기 결과는 `coursespec verify-lms` 로 오프라인 비교합니다. 이전 exporter 실측: 모듈 제목·토론·과제는 일치, `page` 는 `File`(`w1-reading.html`, `w2-case.html`)로 가져와짐, CC QTI 퀴즈는 모듈·classic quizzes·과제 목록에 없음, 토론은 제목만 있고 점수 없음(CC 토론 리소스에 점수 필드 없음), 성적 카테고리(참여/과제)는 들어오지 않고 Canvas 기본 그룹(`Assignments`, `Imported Assignments`)만 있음. New Quizzes API 가 없는 오픈소스 canvas-lms 인스턴스라 New Quiz 생성·문항 단계는 404(비JSON)로 실패했고, 퀴즈 id 가 없어 문항 단계는 호출하지 못했습니다. 루브릭은 이 데모 계획에 없습니다. 현재 exporter 는 `page` 를 `wiki_content/` 로 내보내고, 가져오기 뒤 남는 차이는 `--post-import` 보완 단계가 REST 로 처리합니다. 2026-11-15(Asia/Seoul) 새 테스트 강좌(course_id=2, 빈 DB) 실서버 검증에서는 `wiki_content/` 페이지 IMSCC 가져오기가 5초에 끝나고 workflow 가 완료됐으며 issues 는 비어 있었습니다. 이어서 `--canvas-quiz classic` post-import 8단계가 모두 통과했고 Canvas 는 14:05:03 KST 에 Stopped 를 확인했습니다. 가져오기 직후에는 이전과 같은 차이가 남았고, post-import 뒤에는 File→Page·토론 점수·과제/퀴즈 due·성적 그룹/가중치·완료 조건·퀴즈 모듈 배치가 일치했습니다. 남은 격차는 아래 실서버 검증·문항 절에 적었고, 같은 날 이어진 라이브 확인(14:14:44–14:15:21 KST)에서 classic 퀴즈 재저장 PUT과 단원 `opens_day`→모듈 `unlock_at` 패치가 일치했습니다.

## IMS Common Cartridge 1.3 (파일 내보내기)

`coursespec export --format imscc` 는 MCP 없이 LMS 가져오기 파일을 만드는 경로입니다.
ZIP 루트의 `imsmanifest.xml`, organization `rooted-hierarchy`, 상위 `LearningModules` item(제목 없음) 아래에
단원 item 과 활동 item 을 둡니다. `coursespec verify` 가 공식 1EdTech XSD 로 로컬 검증합니다.

| CourseSpec | CC 1.3 리소스 | 비고 |
|---|---|---|
| 과정·단원 | organization + item | 단원 item 에 `title` 필요 |
| `page` | `webcontent` (`wiki_content/<id>.html`) | 완전한 HTML 문서(charset·`<title>`·meta identifier). `video_url` 은 링크로 넣고 info |
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

### Canvas 가져오기 후 보완 (`plan --post-import`)

`page` 는 Canvas 카트리지 importer 의 `WIKI_FOLDER`(`wiki_content/`) 아래 HTML 로 들어갑니다.
다만 표준 CC importer 의 webcontent 변환은 기본적으로 `File` 이며, 기능 플래그
`common_cartridge_page_conversion` 이 켜져야 Page 가 됩니다. 그래서 exporter 결과만으로 Page 가
보장되지 않습니다. `plan --target canvas --course-id N --post-import` 는 강좌·모듈·활동을 다시 만들지 않고,
가져온 강좌를 제목으로 찾아 다음만 보완합니다.

| 보완 | 전용 단계 | 내용 |
|---|---|---|
| 성적 그룹·가중치 | `canvas_ensure_assignment_groups` | 카테고리 id·이름·가중치를 보장하고 `weighted_mean` 이면 가중치 적용 |
| 페이지 | `canvas_promote_file_to_page` | `wiki_content/` 에서 `File` 로 들어온 페이지를 Page 로 교체 (`body_from: imported_file`) |
| 토론 점수 | `canvas_patch_imported` (`kind: discussion`) | 채점 토론의 `points_possible`·과제 그룹·마감 |
| 활동 날짜 | `canvas_patch_imported` | 활동의 `unlock_at` / `due_at` / `lock_at` |
| 완료 조건 | `canvas_patch_imported` (`kind: module_item`) | 기존 COMPLETION 매핑으로 모듈 아이템 요구사항 설정 |
| 퀴즈 | `canvas_create_classic_quiz` 또는 New Quiz 단계 | `--canvas-quiz classic` 또는 `new` (기본 `new`). Classic 은 문항 POST 뒤 같은 퀴즈를 PUT(`notify_of_update: false`)으로 재저장해 목록의 `question_count`/`points_possible` 갱신을 유도 |
| 단원 공개일 | `canvas_patch_imported` (`kind: module`) | 단원 `opens_day` 를 모듈 `unlock_at` 으로 설정 (설계서 시간대 기준 하루 시작) |

Classic 퀴즈는 문항을 모두 POST 한 뒤 같은 퀴즈를 PUT(`{"quiz": {"notify_of_update": false}}`)으로
재저장합니다. Canvas 목록 API 가 재저장 전까지 `question_count` 0·`points_possible` null 을 유지할 수
있기 때문이며, 게시 상태는 바꾸지 않습니다.

`--post-import` 는 `--course-id` 가 필요합니다. 보완 단계는 실행기가 제목(`title`, `unit_title`)으로
가져온 항목을 찾아 적용합니다. 보완해도 옮길 수 없는 것(동료 평가의 평가 점수, 용어집의 토론 자동 변환 등)만
`loss`/`warn` 으로 남깁니다.

### 실서버 검증 (2026-11-15, Asia/Seoul)

새 테스트 강좌(course_id=2, 빈 DB, 이전 검증과 다른 강좌)에 `wiki_content/` 페이지가 든 IMSCC 를
`common_cartridge_importer` 로 가져왔습니다. 가져오기는 5초에 끝났고 workflow 는 완료, issues 는 비어
있었습니다. 이어서 `--canvas-quiz classic` post-import 8단계를 실행해 모두 통과했고, Canvas 는
14:05:03 KST 에 `stop.sh` 로 Stopped 를 확인했습니다.

가져오기 직후(패치 전, 첫 실행과 같음):

- 페이지가 여전히 `File`(`w1-reading.html`, `w2-case.html`)이고 pages 목록이 비어 있었습니다. `wiki_content/`
  경로만으로는 `common_cartridge_page_conversion` 없이 Page 가 되지 않음을 확인했습니다.
- CC QTI 퀴즈가 모듈·classic quizzes·과제 목록에 없었고 migration issues 도 비어 있었습니다.
- 토론은 제목만 들어오고 점수는 `null` 이었습니다.
- 성적 그룹은 `Assignments` / `Imported Assignments` 만 있었습니다.
- New Quizzes API 는 여전히 404 였습니다.

post-import 패치 뒤:

| 항목 | 상태 | 비고 |
|---|---|---|
| 페이지: 읽기 — 편향, 개인정보, 책임 | 일치 | 모듈 type Page, pages 목록에 포함 |
| 페이지: 사례 — 채용 AI와 개인정보 | 일치 | 모듈 type Page, pages 목록에 포함 |
| 토론 점수 | 일치 | 10점, 과제 그룹 참여(가중치 20) |
| 날짜(과제 due) | 일치 | 2027-03-15T23:59+09:00 (저장 2027-03-15T14:59:00Z) |
| 날짜(퀴즈 due) | 일치 | 2027-03-08T23:59+09:00 (저장 2027-03-08T14:59:00Z) |
| 성적 그룹 | 일치 | 참여 20, 과제 80 생성·가중치 적용. 기본 그룹 `Assignments` / `Imported Assignments` 는 잔존 |
| 완료 조건 | 일치 | must_view / must_contribute / min_score 6 / must_view / must_submit |
| 퀴즈 모듈 배치 | 일치 | "1주차 확인 퀴즈"가 1주차 모듈에 Quiz 로 배치됨. due·과제 그룹 설정, create API 통과(id=1) |
| 퀴즈 문항·점수 | 일치 (라이브 확인) | 재저장 전 GET `/questions` 는 문항 2개(1점 multiple_choice_question answers=3, 1점 true_false_question answers=2, points_sum 2.0)를 반환했으나 목록/show API 는 `question_count` 0·`points_possible` null·`published` false 였음. PUT 재저장 200 뒤 show API 는 `question_count` 2·`points_possible` 2.0, `published` false 유지(게시 불필요) |
| 단원 opens_day (2주차 unlock) | 일치 (라이브 확인) | 2주차 모듈(id=4) `unlock_at` null → PUT `2027-03-09T00:00:00+09:00`(opens_day 8, start 2027-03-02, Asia/Seoul 하루 시작) 200 → GET `2027-03-08T15:00:00Z`(같은 시각), match true |
| 가져온 HTML 파일 | 잔존 | File 아이템이 Page 로 교체된 뒤에도 `w1-reading.html` / `w2-case.html` 파일이 남음(info, 기능 손실 아님) |

### 재저장·unlock_at 라이브 확인 (2026-11-15, 14:14:44–14:15:21 KST)

같은 테스트 인스턴스(course_id=2, quiz id=1, module id=4)에서 웹 전용으로 두 보완을 다시 확인했습니다.
잡(job)은 시작하지 않았고 대구교대 인스턴스는 건드리지 않았습니다. Canvas 는 14:14:44–14:15:21 KST
동안 가동했고(`start.sh` 14:15:15 ok, REST 완료 뒤 `stop.sh` 14:15:21 종료), 이후 colima `canvas`
프로필이 Stopped 인 것을 확인했습니다.

- classic 퀴즈: 재저장 전에도 GET `/api/v1/courses/2/quizzes/1/questions` 는 문항 2개
  (문항 1 `multiple_choice_question` 1점 answers=3, 문항 2 `true_false_question` 1점 answers=2,
  points_sum 2.0)를 반환했습니다. 하지만 목록/show API 는 여전히 `question_count` 0,
  `points_possible` null, `published` false 였습니다. PUT `/api/v1/courses/2/quizzes/1`
  `{"quiz":{"notify_of_update":false}}` 가 200 을 반환한 뒤 show API 는 `question_count` 2,
  `points_possible` 2.0 으로 갱신됐고 `published` 는 false 로 유지됐습니다. 게시는 필요 없었습니다.
- 단원 공개일: 2주차 모듈(id=4, "2주차 — 사례 분석과 실천 원칙")의 `unlock_at` 은 null 이었습니다.
  PUT `unlock_at=2027-03-09T00:00:00+09:00`(opens_day 8, start 2027-03-02, Asia/Seoul 하루 시작)이
  200 을 반환했고, GET 은 `2027-03-08T15:00:00Z`(같은 시각)를 반환했습니다. match true.

남은 손실·격차:

- CC QTI 퀴즈는 QTI 도구가 없는 인스턴스라 가져오기에서 계속 빠집니다.
- 표준 CC 가져오기는 페이지를 여전히 `File` 로 저장하며, REST promote 가 이를 교체합니다.
- classic 퀴즈 문항 수·점수는 재저장 PUT 뒤 목록/show API 에서 `question_count` 2·`points_possible` 2.0 으로 확인했습니다(2026-11-15 라이브). `published` 는 false 로 유지되며 게시가 필요 없었습니다.
- 단원 `opens_day` / 모듈 `unlock_at` 은 2주차 모듈(id=4)에서 PUT 뒤 GET 이 같은 시각(`2027-03-08T15:00:00Z`)을 반환해 일치했습니다.
- New Quizzes 는 이 인스턴스에서 여전히 404 입니다(예상된 한계).
- 가져온 HTML 파일(`w1-reading.html`, `w2-case.html`)이 남습니다(info, 기능 손실 아님).
- Canvas 기본 과제 그룹(`Assignments`, `Imported Assignments`)이 `참여`/`과제` 와 함께 남습니다.

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
| `quiz` | `create_quiz` + `add_quiz_questions` | New Quiz(기본) 또는 Classic Quiz + 문항 + Assignment 아이템 | `--canvas-quiz classic` 은 Classic REST, 문항 변환은 아래 |
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

| CourseSpec | Moodle | Canvas New Quizzes | Canvas Classic |
|---|---|---|---|
| multichoice (단일 정답) | multichoice single, 정답 fraction 1 | `choice` / Equivalence | `multiple_choice_question`, 정답 `answer_weight` 100 |
| multichoice (`multiple`) | multichoice, 정답마다 1/n | `multi-answer` / AllOrNothing (warn: 부분 점수 없음) | `multiple_answers_question`, 정답마다 100 |
| truefalse | truefalse | `true-false` | `true_false_question` |
| shortanswer | shortanswer, 인정 답안마다 fraction 1 | loss: `essay`(수동 채점)로 변환 | `short_answer_question`, 인정 답안마다 100 |
| essay | essay + graderinfo | `essay` | `essay_question` |
| 보기별 feedback | 답안 feedback | info: 배포 안 됨 | `answer_comments` |

Classic 퀴즈는 `POST /api/v1/courses/:id/quizzes` 와
`POST /api/v1/courses/:id/quizzes/:quiz_id/questions` 를 씁니다(별도 verify 플래그 없음).
시도·채점·시간제한은 `allowed_attempts`(0=무제한은 -1), `scoring_policy`(`keep_highest`/`keep_latest`),
`time_limit`(분)으로 옮깁니다. 평균·첫 시도 채점은 Classic 이 지원하지 않아 warn 을 남기고 최고 점수를 유지합니다.

CC QTI 리소스 type 은 표준 importer 의 퀴즈 매칭에 맞습니다. 그래도 퀴즈가 조용히 빠지는 주된 원인은
오픈소스 Canvas 에서 QTI converter 플러그인이 꺼져 있을 때(`Qti.qti_enabled?` 가 거짓) importer 가
경고 없이 퀴즈 변환을 건너뛰기 때문입니다. 이번 오픈소스 테스트 인스턴스에서는
`vendor/QTIMigrationTool` / `migrate.py` 가 없었습니다(`QTI_TOOL=no`). 이는 QTI 가 켜지지 않으면
`convert_quizzes` 가 건너뛰어지고 migration warning 도 남지 않는다는 이전 판독과 맞습니다.
플러그인 설정 자체는 확인하지 못했습니다(실행 직후 VM 종료). New Quizzes 는 호스팅 Canvas 에서만 형식
검증이 가능하므로, 오픈소스/테스트 인스턴스에서는 `--canvas-quiz classic` 과 `--post-import` 생성을 씁니다.

## 새 LMS 추가하기

1. `src/coursespec/publishers/<lms>.py`에 `plan_<lms>(spec, start, ...) -> Plan`을 만듭니다.
2. 위 표에 열을 추가하고, 대응이 없는 기능은 `plan.note(where, "loss", ...)`로 숨김없이 보고합니다.
3. `publishers/__init__.py`의 `TARGETS`에 등록하고, 예시 설계서로 "모든 참조가 풀린다"는 테스트를 추가합니다 (`tests/test_canvas.py` 참고).

IMS Common Cartridge 1.3 파일 내보내기는 v0.2.1에서 완료했습니다(위 절 참고). 남은 후보: COURSEMOS LXP.
