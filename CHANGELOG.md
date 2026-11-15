# 변경 내역

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
