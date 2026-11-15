# 로드맵

## v0.1 — 설계서와 계획
- [x] JSON Schema, 예시 설계서
- [x] 린트: 참조·순환·날짜·완료 조건·문항·루브릭, 구성적 정렬, 학습 부담
- [x] Moodle 계획 (moodle-agent-mcp 도구 기준), ID number 기록
- [x] Canvas 계획 초안 (REST v1 / New Quizzes), 변환 보고서
- [ ] 테스트 강좌에서 Moodle 계획 실서버 실행 검증 (데모 영상의 4주차 강좌 재현)
- [x] Canvas 로컬 테스트 인스턴스에서 `verify` 단계 형식 확인: New Quizzes API가 없어 404(비JSON). 퀴즈 id가 없어 문항 단계는 호출하지 못함

## v0.2 — 자료와 수업 생성 연동
- [x] 자료 매니페스트 (`materials`): 단원·학습목표 연결, 용도(generation·tutor·learner), 권리
- [x] OpenMAIC 생성 계획 (`--target openmaic`): 자료 업로드 → 생성 → 스냅샷 → 설계서 기록
- [x] 수업 참조 (`lecture.classroom`)와 Moodle `lecture_id` 연결, Canvas 내보내기 대체 경로
- [x] 검증된 JSON Patch 편집 (`coursespec patch`), 주석 보존
- [x] 튜터 팩 (`coursespec tutor-pack`): 학습목표 지도, 튜터 자료, 학업 정직성 규칙, SKILL.md
- [ ] OpenMAIC 실서버에서 자료 업로드·생성·스냅샷 검증, mod_openmaic `lecture_id` 호환 확인

## v0.2.1 — CC 내보내기와 설계 스킬
- [x] IMS Common Cartridge 1.3 내보내기 (`coursespec export --format imscc`)
- [x] 공식 1EdTech XSD 기반 로컬 검증 (`coursespec verify`), ZIP 참조·가져오기 호환성 점검
- [x] 표준 CC 에 없는 기능의 변환 보고서(info/warn/loss)
- [x] 과정 설계 에이전트 최소 스킬 (`skills/design-agent/SKILL.md`)과 데모
- [x] 내보낸 `.imscc` 를 Canvas 로컬 테스트 인스턴스에서 가져오기 검증: 모듈 제목·토론·과제 일치, `page`는 `File`, CC QTI 퀴즈 누락, 토론 점수 없음, 성적 카테고리 미반영
- [ ] 내보낸 `.imscc` 를 Moodle 실제 인스턴스에서 가져오기 검증
- 범위 밖으로 남김: DeepTutor 연결, xAPI, COURSEMOS 퍼블리셔, 실행기(apply)

## v0.3 — 실행과 재배포 (현재)
- [x] ID number·배포 기록 기반 매칭과 네트워크 없는 diff 계획 (`coursespec diff`, 생성·수정·숨김)
- [x] 마지막 배포 기록 대비 드리프트 보고와 `--accept-drift` 승인, 삭제 없는 숨김 제안
- [x] 새 강좌 `visible`·`enablecompletion` 명시와 OpenMAIC 미분류 성적 항목 수정
- [x] Canvas IMSCC 가져오기 스냅샷과 REST plan verify 단계를 설계서와 비교하는 오프라인 `coursespec verify-lms`
- [x] IMSCC exporter 의 `page` 를 `wiki_content/` 완전한 HTML 문서로 내보내 Canvas 카트리지 importer 경로에 맞춤
- [x] Canvas `--post-import`: 가져온 강좌를 제목으로 찾아 `File→Page`, 토론 점수·날짜·성적 그룹/가중치·완료 조건을 REST 계획으로 보완
- [x] Canvas `--canvas-quiz classic`: Classic Quiz REST 로 퀴즈·문항 생성 (기본값 `new` 는 New Quizzes 경로 유지)
- [x] 오픈소스/테스트 Canvas 에서 `--canvas-quiz classic` + `--post-import` 실행 검증 (2026-11-15, 새 테스트 강좌 course_id=2, 8단계 통과)
  - 남은 격차: classic 퀴즈 문항 수/점수가 목록 스냅샷에서 `question_count 0`·`points_possible null` 로 확인되지 않았고(문항 POST 는 오류 없이 통과, Canvas 종료 직후라 GET 미확인), 단원 `opens_day` 의 모듈 `unlock_at` 은 아직 보완하지 않음
- [ ] 허브에 실행기(apply) 탑재: 계획 미리보기 → 일괄 승인 → 실행 → 배포 기록
- [ ] moodle-agent-mcp 보강 제안 반영 ([publishing.md](publishing.md))

## v0.4 — 설계 워크스페이스와 운영 피드백
- [x] 설계 에이전트 최소 스킬: 설계서 작성·린트 루프·패치 전용 수정 (v0.2.1)
- [ ] OpenMAIC 내보내기(HTML·MP4) 자동화와 `lecture.exports` 기록
- [ ] 허브 LLM 관문: OpenMAIC·DeepTutor 엔드포인트 연결, 스트리밍 지원, 자유 대화문 가명처리 검증
- [ ] DeepTutor 연결: 학습자 단위 권한, 튜터 팩 로딩
- [ ] 방법론 스킬: 백워드 디자인, ADDIE, 플립러닝, KOICA PDM 연계
- [ ] 운영 결과 집계(가명처리, xAPI + `cs:` 식별자) → 다음 학기 개정 제안 (JSON Patch)

## 이후
- [ ] COURSEMOS 퍼블리셔
- [ ] Instructure 공식 Canvas MCP 일반 출시 시 Canvas 퍼블리셔 전환
- [ ] 스키마 v1.0 고정과 호환성 정책
