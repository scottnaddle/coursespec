---
name: design-agent
description: 강의계획서(hwp/hwpx/docx/pdf에서 추출한 텍스트)를 CourseSpec YAML로 설계하고, lint 루프와 검증된 JSON Patch만으로 다듬는 과정 설계 스킬. 배포·계획 실행·LMS 호출은 하지 않는다.
---

# 과정 설계 에이전트 스킬

교수자가 건넨 강의계획서(syllabus) **텍스트**(hwp/hwpx/docx/pdf에서 이미 추출된 것)를 읽고,
이 저장소의 CourseSpec 설계서로 옮깁니다. 이 스킬은 설계까지만 합니다.
퍼블리시(배포)·계획 실행(apply)·LMS 호출은 다른 도구의 몫이며 여기서 하지 않습니다.

## 입력

- 강의계획서 텍스트. 바이너리 문서를 직접 파싱하지 않습니다. 텍스트가 없으면 교수자에게 요청합니다.
- 과정 이름, 주차 구성, 학습목표, 평가 방식, 과제·토론·퀴즈 설명이 보통 들어 있습니다.
- **학생 개인정보, 토큰·비밀번호·API 키, 실제 LMS 주소(호스트명·IP)를 설계서에 넣지 않습니다.**
  예시나 테스트 값이 필요하면 가상의 값을 씁니다.

## 1. 설계서 초안 작성

`docs/spec-guide.md`와 `schema/coursespec.schema.json`을 먼저 읽습니다. 그다음 YAML 초안을 만듭니다.

- `coursespec: "0.2"`, `id`, `title`, `units`는 필수입니다.
- `outcomes`에는 관찰 가능한 학습목표를 두고, 활동·문항이 `outcomes`로 참조하게 합니다.
- 모든 날짜는 절대 날짜가 아니라 과정 시작일 기준 상대 일수(`opens_day`, `due_day`, `cutoff_day`)로 적습니다.
- 활동 유형은 `page`, `file`, `assignment`, `quiz`, `discussion`을 우선 사용하고,
  필요할 때만 `peer_review`, `wiki`, `glossary`, `survey`, `h5p`, `interactive_lecture`를 씁니다.
- 평가는 `grading.categories`와 활동의 `grading.category`로 연결합니다.
- 파일 경로는 실제 학생 정보가 없는 워크스페이스 상대 경로만 씁니다.

## 2. lint 루프

초안을 저장한 뒤 다음을 반복합니다.

```bash
coursespec validate course.coursespec.yaml
coursespec lint     course.coursespec.yaml
```

- **린트 오류가 0건이 될 때까지 고칩니다.** 검증(schema) 오류도 먼저 해결합니다.
- 경고는 가능하면 줄입니다. 특히 학습목표–활동–평가 정렬(W101–W103), 성적 가중치(W104),
  학습 부담(W105), 성적 카테고리 누락(W109)을 확인합니다.
- 오류를 없애기 위해 학생 정보나 실제 서버 정보를 채워 넣지 않습니다.

## 3. 저장 후에는 패치로만 수정

설계서 파일이 한 번 저장된 뒤에는 **절대 파일을 통째로 다시 쓰지 않습니다.**
모든 추가 수정은 RFC 6902 JSON Patch를 `coursespec patch`로 적용합니다.
이 명령은 스키마와 린트 오류를 검사하고, 실패하면 파일을 바꾸지 않으며 YAML 주석을 보존합니다.

```bash
coursespec patch course.coursespec.yaml ops.json          # 적용
coursespec patch course.coursespec.yaml ops.json --dry-run # 미리보기
```

패치 연산은 `add`, `replace`, `remove`, `test`만 씁니다. 예:

```json
[
  {"op": "replace", "path": "/units/0/items/0/title", "value": "읽기 — 핵심 쟁점"},
  {"op": "add", "path": "/units/1/items/-", "value": {"id": "w2-check", "type": "page", "title": "정리", "content": "핵심 요약", "completion": {"mode": "view"}}}
]
```

패치가 거부되면 오류 메시지를 읽고 더 작은 패치로 다시 시도합니다.

## 4. 하지 않는 일

- `coursespec plan`으로 배포 계획을 만들거나 실행하지 않습니다.
- Moodle·Canvas·OpenMAIC 등 어떤 LMS/서버도 호출하지 않습니다.
- 네트워크에서 자료를 내려받거나 실제 호스트 주소를 확인하지 않습니다.
- 교수자 승인 없이 설계서를 확정하거나 배포하지 않습니다.

## 완료 기준

- `coursespec validate`와 `coursespec lint`가 오류 0건입니다.
- 학습목표가 활동과 평가에 고르게 연결되어 있습니다.
- 남은 경고가 있다면 교수자에게 무엇을 검토해야 하는지 한국어로 설명합니다.
