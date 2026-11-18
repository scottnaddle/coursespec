# 변경 내역

## Unreleased
- 교수용 웹 UI M2 — 화면 03 「과정 지도」: 초안 인계 → 설계 에이전트가 CourseSpec 설계서를 생성(스텁은 네트워크 없이 결정적, 스키마·린트 오류 0) → 주차·학습목표·평가 비중·활동을 한국어 카드로 확인
- 설계서 → 화면 모델 API(`GET /api/designs/{id}` 등): 요약 칩(주차 수·학습목표 수·평가 비중·주당 최대 학습시간), 학습목표 카드(블룸 수준 한국어), 주차 카드(활동 유형 한국어 배지·분·N일차 마감), 린트 결과는 코드 없는 쉬운 한국어 notice(오류/경고·위치 라벨). 린트 0 예시에서는 배너가 뜨지 않음
- 설계서 편집(`POST /api/designs/{id}/edits`): 주차 제목·요약, 활동 제목·분·마감 수정과 활동 추가·삭제·이동은 서버가 `test`+`replace`/`add`/`remove` JSON Patch 로 변환해 `coursespec patch`(`apply_ops`/`patch_file`)로 검증 적용. 스키마·린트 오류 시 4xx 쉬운 한국어 안내와 파일 불변, YAML 주석 보존
- “수정 요청”(`change-requests`): 자유 문장 → 설계 에이전트(스텁/실모델)가 검증 패치 생성 → 변경 요약 미리 보기(패치 원문 미노출) → 적용/취소. 적용은 저장해 둔 패치를 다시 검증(그사이 바뀌면 쉬운 안내), 못 알아들은 문장은 400 안내
- “이 설계로 확정”(`confirm`): 린트 오류 0일 때만 확정 상태 저장. plan/export/LMS 호출 없음
- 예시 과정 열기(`POST /api/designs/example`): `examples/` 원본을 바꾸지 않는 작업 공간 복사본으로 열기
- 설계 에이전트 LLM 호출 범위: 설계서 생성·수정 요청 해석에만. 실모델 경로는 M1 초안과 같은 방식(키·주소 경로만, `COURSESPEC_LLM_STUB=1` 또는 호출 주입으로 네트워크 없이 테스트)

## 0.3.0
- IMSCC exporter: `page` 를 완전한 HTML 문서(`charset`·`<title>`·meta identifier)로 `wiki_content/<id>.html` 에 내보냄. `file`·`wiki`·`glossary`·강의 HTML 경로는 그대로
- Canvas `--post-import`: 기존 `--course-id` 강좌를 제목으로 찾아 강좌·모듈·활동을 다시 만들지 않고 `canvas_ensure_assignment_groups`·`canvas_patch_imported`·`canvas_promote_file_to_page`·`canvas_create_classic_quiz` 단계로 점수·날짜·가중치·완료 조건·File→Page 를 보완. `--course-id` 없이는 종료 코드 2
- Canvas `--post-import`: 단원 `opens_day` 를 `canvas_patch_imported`(`kind: module`)로 모듈 `unlock_at` 에 설정 (설계서 시간대 기준 하루 시작). 더 이상 `loss` 로 보고하지 않음
- Canvas `--canvas-quiz classic|new`(기본 `new`): classic 은 `/api/v1/courses/:id/quizzes`·`/questions` 로 고전 퀴즈·문항 생성, new 는 기존 New Quizzes 경로(`verify=True`) 유지
- Classic 퀴즈 계획: 문항 POST 뒤 `/api/v1/courses/:id/quizzes/:quiz_id` PUT(`{"quiz": {"notify_of_update": false}}`)으로 재저장. 목록 API 가 재저장 전까지 `question_count` 0·`points_possible` null 을 유지할 수 있기 때문이며, 자동 게시는 하지 않음
- Classic 문항 매핑: multichoice→`multiple_choice_question`(복수 정답은 `multiple_answers_question`), truefalse→`true_false_question`, shortanswer→`short_answer_question`, essay→`essay_question`. 시도·채점·시간제한은 `allowed_attempts`·`scoring_policy`·`time_limit` 으로 변환
- 문서에 QTI converter 플러그인(`Qti.qti_enabled?`)이 꺼진 오픈소스 Canvas 에서 퀴즈가 경고 없이 빠지는 원인과 Classic+post-import 우회 경로를 기록. 실서버 인스턴스에는 `vendor/QTIMigrationTool` / `migrate.py` 가 없었고(`QTI_TOOL=no`), 플러그인 설정은 확인하지 못함
- 오픈소스 Canvas 실서버 검증(2026-11-15, Asia/Seoul, 새 테스트 강좌 course_id=2): `wiki_content/` 페이지 IMSCC 가져오기 5초·workflow 완료·issues 없음, 이어서 `--canvas-quiz classic` post-import 8단계 통과. File→Page·토론 점수·과제/퀴즈 due·성적 그룹/가중치·완료 조건·퀴즈 모듈 배치는 일치. 남은 격차: classic 퀴즈 문항 수/점수는 목록 스냅샷에서 확인되지 않음(`question_count 0`, `points_possible null`), CC QTI 퀴즈는 QTI 도구 부재로 가져오기에서 계속 빠짐
- Classic 퀴즈 재저장 PUT 라이브 확인(2026-11-15, Asia/Seoul, course_id=2, quiz id=1, 웹 전용·잡 미시작·대구교대 미접촉): Canvas 14:14:44–14:15:21 KST 가동(start.sh 14:15:15 ok, REST 완료 뒤 stop.sh 14:15:21 종료), 이후 colima canvas 프로필 Stopped 확인. 재저장 전 GET `/api/v1/courses/2/quizzes/1/questions` 는 이미 문항 2개(문항 1 `multiple_choice_question` 1점 answers=3, 문항 2 `true_false_question` 1점 answers=2, points_sum 2.0)를 반환했지만 목록/show API 는 `question_count` 0·`points_possible` null·`published` false 였음. PUT `/api/v1/courses/2/quizzes/1` `{"quiz":{"notify_of_update":false}}` 200 뒤 show API 는 `question_count` 2·`points_possible` 2.0, `published` false 유지(게시 불필요)
- 단원 `opens_day`→모듈 `unlock_at` 라이브 확인(2026-11-15, Asia/Seoul, course_id=2, module id=4): 2주차 모듈 "2주차 — 사례 분석과 실천 원칙" 의 `unlock_at` 이 null 이었고, PUT `unlock_at=2027-03-09T00:00:00+09:00`(opens_day 8, start 2027-03-02, Asia/Seoul 하루 시작) 200 뒤 GET 은 `2027-03-08T15:00:00Z`(같은 시각)를 반환, match true
- `coursespec diff SPEC --target moodle --course-id N --start YYYY-MM-DD --outline FILE`: 설계서와 실행기가 읽어 온 LMS 스냅샷(`get_course_outline`, 선택 `gradebook_overview`, 배포 기록)의 차이 계획. 네트워크 호출·삭제 없음
- diff 매칭: `cs:<설계서 id>:<활동 id>` ID number → 배포 기록 cmid → 같은 섹션·modname·이름. 모호하면 추측하지 않음
- diff 동작: create·update·hide(숨김)만 만들고, 마지막 배포 이후 LMS에서 직접 바뀐 값은 드리프트로 보고. `--accept-drift` 없이는 덮어쓰지 않고 종료 코드 2
- 배포 기록(record) JSON 형식과 apply 후 기록 절차 문서화, diff 결과에 제안 record 포함
- Moodle 새 강좌 `create_course`에 `visible`(기본 0)와 `enablecompletion`(기본 1) 포함. CLI `--visible`, `--enable-completion/--no-enable-completion`
- 새 강좌의 기본 공지 포럼은 수정·숨김·삭제하지 않는다는 변환 보고 추가
- OpenMAIC 강의 성적 처리 수정: 성적 설정이 없으면 grade 0으로 만들고 경고, 범주 없는 성적은 미분류 항목이 됨을 경고. 예시 w4 강의의 불필요한 100점 항목 제거
- `coursespec verify-lms SPEC --target canvas --snapshot FILE [--verify-steps FILE] [--json]`: 실행기가 읽어 둔 Canvas REST 스냅샷과 REST plan verify 단계 결과를 설계서와 오프라인 비교. 모듈·페이지·토론·과제·퀴즈별 `일치`/`누락`/`차이`, 표준 CC 한계 보고, 절대 URL verify 단계 거절, 종료 코드 0/1/2
- 로컬 Canvas 테스트 인스턴스 IMSCC 가져오기 실측: 모듈 제목·토론·과제 일치, `page`는 `File`(`w1-reading.html`, `w2-case.html`), CC QTI 퀴즈 누락, 토론 점수 없음, 성적 카테고리 미반영. New Quizzes API 부재로 REST plan verify 단계는 404(비JSON)
- 교수용 웹 UI (M1, `src/coursespec/web/` + `web/`): FastAPI 백엔드가 `coursespec` 패키지를 감싸고, Vite + React + TypeScript 프론트. 목업 01·02(새 과정 시작·강의계획서 초안 검토)와 앱 셸(사이드바·상단바) 구현
- 실라버스 초안 생성: 과목 이름(필수)＋목표·자료(선택)로 제목·소개·학습목표·주차·평가·제안 JSON 초안. 키·주소는 환경변수 경로만(`COURSESPEC_LLM_KEY_PATH` 등), 값은 로그·응답에 남기지 않음. `COURSESPEC_LLM_STUB=1` 또는 호출 객체 주입으로 네트워크 없이 결정적 스텁 초안(자료 키워드 예: “윤리”가 주차·제안에 반영)
- 자료 텍스트 추출: txt/md(UTF-8), PDF(pypdf), DOCX(python-docx), HWPX(내부 XML). 구형 HWP 바이너리는 쉬운 한국어 오류로 안내. 파일별 실패를 보고하고 과목 이름만으로도 초안 생성 계속
- HTTP API: `GET /api/health`, `POST /api/drafts`(multipart), `GET/PATCH /api/drafts/{id}`, `regenerate`, `suggestions/{sid}/accept·skip`(수락 시에만 본문 반영), `handoff`(설계 에이전트용 강의계획서 텍스트, 설계서 생성·LMS 호출 없음). 오류는 한국어 `message`로 원인·다음 행동 안내, 과목 이름 없음은 4xx
- 과정 초안은 서버 쪽 작업 공간(`COURSESPEC_WEB_WORKSPACE`, 없으면 `var/workspace`, gitignore)에 YAML 로 저장하되 화면·API 는 구조화 JSON 만. 기본 화면에 YAML·JSON Patch·도구 이름을 보여 주지 않음
- 로그 적색: 토큰·Bearer·API 키, 쿼리스트링 key, 자격증명이 박힌 URL 을 로그에서 감춤 (`src/coursespec/web/redact.py`)
- 의존성: optional extra `web`(fastapi, uvicorn, python-multipart, pypdf, python-docx, httpx) 추가. 기본 설치 부풀리지 않고 CI 는 `pip install -e ".[test,web]"` 로 최소 수정
- 프론트 테스트(Vitest + Testing Library)와 백엔드 웹 테스트(`tests/test_web_*.py`) 추가: 기존 71개 유지 + 신규 테스트

## 0.2.1
- `coursespec export SPEC --format imscc`: IMS Common Cartridge 1.3 ZIP 내보내기 (네트워크 호출 없음)
- `coursespec verify PACKAGE.imscc`: 공식 1EdTech XSD 와 ZIP 참조·가져오기 호환성 로컬 검증
- 페이지·파일·과제·퀴즈(QTI 1.2.1 CC 프로필)·토론·동료평가·위키/용어집·강의 내보내기 변환
- 표준 CC 에 없는 배지·완료 조건·선수조건·성적 가중치·날짜는 `info`/`warn`/`loss` 로 보고
- 공식 CC 1.3 / assignment extension XSD 를 `schema/imscc/` 에 그대로 포함 (`schema/imscc/NOTICE.md`)
- `skills/design-agent/SKILL.md` 최소 설계 스킬과 `examples/design-agent-demo/` 데모
- 의존성 추가: lxml

## 0.2.0
- 스펙 `coursespec: "0.2"` (0.1 설계서도 그대로 유효)
- 자료 매니페스트 `materials[]`: 단원·학습목표 연결, `uses`(generation·tutor·learner), `rights`, `sha256`
- `file` 활동이 `source` 대신 `material` 로 자료를 배포할 수 있음
- `lecture` 확장: `engine`, `materials`, `classroom`(생성된 OpenMAIC 수업 기록), `exports`(HTML·동영상·pptx)
- 새 대상 `plan --target openmaic`: 자료 업로드 → 수업 생성 → 문서 스냅샷 → 설계서 기록
- 생성 요구사항에 과정·단원·학습목표(블룸 수준)·분량·언어를 자동으로 덧붙임
- Moodle: 생성된 수업을 `lecture_id` 로 연결 / Canvas: 내보낸 HTML·동영상으로 대체 배포
- `coursespec patch`: 검증된 RFC 6902 JSON Patch 편집, YAML 주석 보존
- `coursespec tutor-pack`: 튜터 팩(JSON)과 SKILL.md, 학업 정직성 규칙 자동 생성
- 린트: E014–E017, W111–W113, W115
- 의존성 추가: ruamel.yaml

## 0.1.0
- 스키마, 린트, Moodle·Canvas 배포 계획, 예시 설계서
