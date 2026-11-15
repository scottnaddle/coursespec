# 변경 내역

## 0.3.0
- IMSCC exporter: `page` 를 완전한 HTML 문서(`charset`·`<title>`·meta identifier)로 `wiki_content/<id>.html` 에 내보냄. `file`·`wiki`·`glossary`·강의 HTML 경로는 그대로
- Canvas `--post-import`: 기존 `--course-id` 강좌를 제목으로 찾아 강좌·모듈·활동을 다시 만들지 않고 `canvas_ensure_assignment_groups`·`canvas_patch_imported`·`canvas_promote_file_to_page`·`canvas_create_classic_quiz` 단계로 점수·날짜·가중치·완료 조건·File→Page 를 보완. `--course-id` 없이는 종료 코드 2
- Canvas `--canvas-quiz classic|new`(기본 `new`): classic 은 `/api/v1/courses/:id/quizzes`·`/questions` 로 고전 퀴즈·문항 생성, new 는 기존 New Quizzes 경로(`verify=True`) 유지
- Classic 문항 매핑: multichoice→`multiple_choice_question`(복수 정답은 `multiple_answers_question`), truefalse→`true_false_question`, shortanswer→`short_answer_question`, essay→`essay_question`. 시도·채점·시간제한은 `allowed_attempts`·`scoring_policy`·`time_limit` 으로 변환
- 문서에 QTI converter 플러그인(`Qti.qti_enabled?`)이 꺼진 오픈소스 Canvas 에서 퀴즈가 경고 없이 빠지는 원인과 Classic+post-import 우회 경로를 기록. 실서버 인스턴스에는 `vendor/QTIMigrationTool` / `migrate.py` 가 없었고(`QTI_TOOL=no`), 플러그인 설정은 확인하지 못함
- 오픈소스 Canvas 실서버 검증(2026-11-15, Asia/Seoul, 새 테스트 강좌 course_id=2): `wiki_content/` 페이지 IMSCC 가져오기 5초·workflow 완료·issues 없음, 이어서 `--canvas-quiz classic` post-import 8단계 통과. File→Page·토론 점수·과제/퀴즈 due·성적 그룹/가중치·완료 조건·퀴즈 모듈 배치는 일치. 남은 격차: classic 퀴즈 문항 수/점수는 목록 스냅샷에서 확인되지 않음(`question_count 0`, `points_possible null`), 단원 `opens_day` 는 모듈 `unlock_at` 으로 보완하지 않아 `loss` 로 보고, CC QTI 퀴즈는 QTI 도구 부재로 가져오기에서 계속 빠짐
- `coursespec diff SPEC --target moodle --course-id N --start YYYY-MM-DD --outline FILE`: 설계서와 실행기가 읽어 온 LMS 스냅샷(`get_course_outline`, 선택 `gradebook_overview`, 배포 기록)의 차이 계획. 네트워크 호출·삭제 없음
- diff 매칭: `cs:<설계서 id>:<활동 id>` ID number → 배포 기록 cmid → 같은 섹션·modname·이름. 모호하면 추측하지 않음
- diff 동작: create·update·hide(숨김)만 만들고, 마지막 배포 이후 LMS에서 직접 바뀐 값은 드리프트로 보고. `--accept-drift` 없이는 덮어쓰지 않고 종료 코드 2
- 배포 기록(record) JSON 형식과 apply 후 기록 절차 문서화, diff 결과에 제안 record 포함
- Moodle 새 강좌 `create_course`에 `visible`(기본 0)와 `enablecompletion`(기본 1) 포함. CLI `--visible`, `--enable-completion/--no-enable-completion`
- 새 강좌의 기본 공지 포럼은 수정·숨김·삭제하지 않는다는 변환 보고 추가
- OpenMAIC 강의 성적 처리 수정: 성적 설정이 없으면 grade 0으로 만들고 경고, 범주 없는 성적은 미분류 항목이 됨을 경고. 예시 w4 강의의 불필요한 100점 항목 제거
- `coursespec verify-lms SPEC --target canvas --snapshot FILE [--verify-steps FILE] [--json]`: 실행기가 읽어 둔 Canvas REST 스냅샷과 REST plan verify 단계 결과를 설계서와 오프라인 비교. 모듈·페이지·토론·과제·퀴즈별 `일치`/`누락`/`차이`, 표준 CC 한계 보고, 절대 URL verify 단계 거절, 종료 코드 0/1/2
- 로컬 Canvas 테스트 인스턴스 IMSCC 가져오기 실측: 모듈 제목·토론·과제 일치, `page`는 `File`(`w1-reading.html`, `w2-case.html`), CC QTI 퀴즈 누락, 토론 점수 없음, 성적 카테고리 미반영. New Quizzes API 부재로 REST plan verify 단계는 404(비JSON)

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
