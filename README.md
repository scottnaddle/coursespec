# CourseSpec

> 교수자가 LMS 밖에서 과정을 설계하고, 배포할 때만 Moodle·Canvas로 내보내는 **LMS 중립 과정 설계서**와 그 퍼블리셔입니다.

[moodle-agent-mcp](https://github.com/scottnaddle/moodle-agent-mcp)가 "에이전트가 Moodle을 다루는 손"이라면, CourseSpec은 그 앞단의 "설계 원본"입니다. 과정 설계 에이전트는 이 설계서를 검증된 패치로 다듬고, 퍼블리셔는 설계서를 각 대상의 호출 계획으로 바꿉니다.

```
교수자 워크스페이스 ──> CourseSpec(원본, 버전 관리) ──> 린트 ──> 퍼블리셔(plan) ──승인──> 실행(apply)
        ▲                                                           ├─ openmaic → 몰입형 수업 생성 → 설계서에 기록
        └──────────── 검증된 JSON Patch ◀───────────────────────────┤
                                                                    ├─ moodle   → moodle-agent-mcp 도구 호출
                                                                    ├─ canvas   → Canvas REST / (향후) 공식 MCP
                                                                    └─ tutor-pack → DeepTutor 등 학습자 튜터 설정
```

OpenMAIC(수업 생성)·DeepTutor(학습자 튜터)와는 직접 결합하지 않고 CourseSpec의 공유 계약(식별자·학습목표·자료 매니페스트)으로 연동합니다: [docs/integration.md](docs/integration.md)

## 왜 별도 설계서인가

- **원본은 교수자 소유**: Moodle은 배포·운영 환경이고, 설계는 그 밖에서 계속 관리됩니다. 학생 개인정보는 설계서에 들어오지 않습니다.
- **LMS 중립**: 같은 설계서를 Moodle과 Canvas에 배포합니다. LMS 간 차이는 퍼블리셔가 *변환 보고서*로 알려 주고, 교수자가 알고 승인합니다.
- **학기 재사용**: 날짜는 "시작일 기준 N일차"로 적고, 배포할 때 실제 날짜를 정합니다.
- **배포 전 검토**: 학습목표–활동–평가 정렬, 선수조건 순환, 성적 가중치, 주차별 학습 부담을 린트로 점검합니다.

자세한 배경은 [docs/concept.md](docs/concept.md)를 보세요.

## 빠른 시작

```bash
pip install -e ".[test]"

coursespec validate examples/ai-agent-education.coursespec.yaml
coursespec lint     examples/ai-agent-education.coursespec.yaml
coursespec plan     examples/ai-agent-education.coursespec.yaml --target moodle --start 2027-03-02
coursespec plan     examples/ai-agent-education.coursespec.yaml --target canvas --start 2027-03-02 --account-id 1
coursespec plan     examples/ai-agent-education.coursespec.yaml --target canvas --start 2027-03-02 \
                    --course-id 5 --post-import [--canvas-quiz classic|new]
coursespec plan     examples/ai-agent-education.coursespec.yaml --target openmaic --server ubion-maic
coursespec plan     ... --json      # 실행기(에이전트·허브)가 읽는 형식

coursespec diff       course.yaml --target moodle --course-id 11 --start 2027-03-02 \
                      --outline outline.json [--gradebook gradebook.json] [--record record.json] [--accept-drift]
coursespec export   examples/ai-agent-education.coursespec.yaml --format imscc --out course.imscc
coursespec verify   course.imscc    # 공식 CC 1.3 XSD 로 로컬 검증 (네트워크 없음)

coursespec verify-lms course.yaml --target canvas --snapshot snapshot.json \
                    [--verify-steps steps.json] [--json]   # 가져오기 결과 오프라인 비교

coursespec patch      course.yaml ops.json [--dry-run]      # 검증된 JSON Patch 수정
coursespec tutor-pack course.yaml --start 2027-03-02 --out tutor/   # tutor-pack.json + SKILL.md
```

`plan`·`diff`·`export`는 네트워크를 호출하지 않습니다. `diff`는 실행기가 읽어 온 LMS 스냅샷 JSON과 마지막 배포 기록을 입력으로 받아 생성·수정·숨김 단계만 만듭니다(삭제 없음). 실행은 계획을 읽은 에이전트나 허브가 합니다 ([docs/publishing.md](docs/publishing.md)).

`export --format imscc`는 IMS Common Cartridge 1.3 ZIP(`imsmanifest.xml`이 ZIP 루트)을 만들고,
같은 검증을 바로 실행합니다. `page`는 Canvas 카트리지 importer가 쓰는 `wiki_content/<id>.html`로 내보내고,
표준 CC importer가 기능 플래그 없이 `File`로 둘 때는 `plan --post-import`가 REST로 Page를 만들어 교체합니다.
표준 CC에 없는 기능은 변환 보고서에 `info`/`warn`/`loss`로 남깁니다.
`verify`는 공식 1EdTech XSD(저장소의 `schema/imscc/`)로 매니페스트·과제·토론·QTI를 오프라인 검증합니다.
`verify-lms`는 `.imscc`를 Canvas에 가져온 뒤 실행기가 REST로 읽어 둔 스냅샷과 설계서를 오프라인 비교합니다.
네트워크를 호출하지 않으며, 같은 방식으로 REST plan의 `verify=True` 단계 실행 결과도 함께 보고합니다.

과정 설계 에이전트는 [skills/design-agent/SKILL.md](skills/design-agent/SKILL.md)를 따릅니다.
강의계획서 텍스트로 초안을 만들고 `coursespec lint` 루프를 돈 뒤, 저장된 설계서는
`coursespec patch`로만 고칩니다. 데모는 [examples/design-agent-demo/](examples/design-agent-demo/)에 있습니다.

## 설계서 한눈에 보기

```yaml
coursespec: "0.2"
id: ai-agent-education
title: AI 에이전트 시대의 교육
outcomes:
  - { id: lo1, statement: AI 에이전트를 스킬·파이프라인·플러그인과 구분해 설명할 수 있다., level: understand }
grading:
  categories: [{ id: quizzes, name: 퀴즈, weight: 20 }, ...]
units:
  - id: w1
    title: 1주차 — AI 에이전트란 무엇인가
    items:
      - { id: w1-reading, type: page, title: 읽기 자료, content: "...", outcomes: [lo1], completion: { mode: view } }
      - id: w1-quiz
        type: quiz
        requires: [w1-reading]
        due_day: 7
        grading: { max: 10, category: quizzes }
        completion: { mode: pass, pass_grade: 6 }
        questions: [...]
```

전체 예시: [examples/ai-agent-education.coursespec.yaml](examples/ai-agent-education.coursespec.yaml) · 필드 안내: [docs/spec-guide.md](docs/spec-guide.md) · 스키마: [schema/coursespec.schema.json](schema/coursespec.schema.json)

## 활동 유형

| 구분 | 유형 | Moodle | Canvas |
|---|---|---|---|
| 공통 코어 | `page` `file` `assignment` `quiz` `discussion` | 대응 | 대응 (일부 옵션 변환) |
| 확장 | `peer_review` | 워크숍 | 동료 검토 과제 (평가 점수 손실) |
| 확장 | `wiki` `glossary` | 위키 · 용어집 | 학생 편집 페이지 · 토론 |
| 확장 | `interactive_lecture` | OpenMAIC (mod_openmaic) | 내보낸 HTML·동영상 (상호작용 손실), 없으면 제외 |
| 확장 | `survey` `h5p` | 피드백 · H5P | 배포 제외 |

변환 규칙 전체: [docs/lms-mapping.md](docs/lms-mapping.md)

## 저장소 구성

| 경로 | 내용 |
|---|---|
| `schema/` | JSON Schema (2020-12)와 공식 CC 1.3 XSD(`schema/imscc/`). 다른 언어 구현도 JSON Schema를 기준으로 합니다 |
| `src/coursespec/` | 로더·린트·타임라인·퍼블리셔·CC 내보내기/검증·CLI (Python 3.11+) |
| `skills/` | 과정 설계 에이전트 스킬(SKILL.md) |
| `examples/` | 예시 설계서와 design-agent 데모 |
| `docs/` | 개념, 작성 안내, LMS 매핑, 배포 프로토콜, 연동(OpenMAIC·DeepTutor), 로드맵 |
| `tests/` | 스키마·린트·퍼블리셔·CC 내보내기/검증·설계 스킬 테스트 |

## 현재 상태 (v0.3.0)

- 스키마·린트·Moodle 계획: moodle-agent-mcp 도구 시그니처 기준으로 작성, 단위 테스트 완료. 실서버 실행 검증은 아직입니다.
- Canvas 계획: REST API v1 / New Quizzes API 기준입니다. IMSCC 가져오기와 REST plan의 `verify=True` 단계를 로컬 Canvas 테스트 인스턴스에서 실행했습니다. 모듈 제목·토론·과제는 일치했습니다. 이전 exporter의 `page`는 `File`(`w1-reading.html`, `w2-case.html`)로 들어왔고, CC QTI 퀴즈는 모듈·classic quizzes·과제 목록에 없었습니다(가져오기 이슈 목록도 비어 있었음). 토론은 제목만 있고 점수는 없었습니다(CC 토론 리소스에 점수 필드 없음). 성적 카테고리(참여/과제)는 들어오지 않고 Canvas 기본 그룹(`Assignments`, `Imported Assignments`)만 있었습니다.
- 이제 exporter는 `page`를 `wiki_content/`로 내보냅니다. 표준 CC importer는 기능 플래그 `common_cartridge_page_conversion`이 없으면 이를 `File`로 둘 수 있어, `--post-import`가 제목으로 찾아 Page로 교체합니다. 같은 보완 단계에서 토론 점수·날짜·성적 그룹/가중치·완료 조건을 REST로 설정합니다.
- 오픈소스 Canvas에서 QTI converter 플러그인이 꺼져 있으면(`Qti.qti_enabled?`가 거짓) importer가 경고 없이 퀴즈를 건너뜁니다. 리소스 type은 표준 importer 매칭에 맞으므로, 테스트용 인스턴스에서는 `--canvas-quiz classic`으로 Classic Quiz를 만들고 `--post-import`로 모듈 아이템을 보완하세요. New Quizzes는 호스팅 Canvas에서만 형식 검증이 가능하며, 오픈소스 canvas-lms 인스턴스에는 `/api/quiz/v1` API가 없을 수 있습니다.
- OpenMAIC 생성 계획: THU-MAIC/OpenMAIC 저장소 코드(2026-11)의 API 기준. 실서버 검증 전입니다.
- IMS Common Cartridge 1.3 내보내기와 로컬 XSD 검증: 완료. Canvas 로컬 테스트 인스턴스 가져오기까지 확인했고, 위 가져오기 차이는 `coursespec verify-lms`로 오프라인 비교합니다.
- `coursespec verify-lms`: 실행기가 읽어 둔 Canvas 스냅샷과 REST plan verify 단계 결과를 설계서와 비교합니다. 네트워크 호출 없이 일치·누락·차이와 표준 CC 한계를 보고하며 종료 코드는 0/1/2입니다.
- 설계 에이전트 스킬(최소): 초안 작성·린트 루프·패치 전용 수정 규칙.
- 튜터 팩: 제품 중립 JSON + SKILL.md. DeepTutor 연결은 학습자 권한 체계 이후입니다.
- 재배포 diff와 드리프트 감지: 실행기가 넘긴 LMS 스냅샷·배포 기록을 쓰는 네트워크 없는 `coursespec diff`로 제공합니다. 실제 apply 실행기는 [로드맵](docs/roadmap.md)에 있습니다. 변경 내역은 [CHANGELOG.md](CHANGELOG.md).

## 교수용 웹 UI (M1: 실라버스 초안)

개발 지식이 없는 교수가 브라우저에서 과목 이름(＋선택 목표·자료)으로 실라버스 초안을 받아
고친 뒤 설계 에이전트 입력으로 넘길 수 있는 웹 UI 입니다. 백엔드는 `src/coursespec/web/`,
프론트는 `web/`(Vite + React + TypeScript)입니다.

```bash
# 백엔드 (FastAPI) — 스텁 모드로 띄우면 네트워크 LLM 호출 없이 초안을 만든다
pip install -e ".[web]"
COURSESPEC_LLM_STUB=1 python -m coursespec.web.main          # 기본 http://127.0.0.1:18080

# 프론트 (개발) — /api 를 백엔드로 프록시 (시스템 기본 Node(v10)는 쓰지 말 것)
cd web && npm install && npm run dev                          # 기본 http://127.0.0.1:15180

# 프론트 검사·빌드 (빌드하면 백엔드가 web/dist 를 함께 서빙)
cd web && npm test && npm run lint && npm run typecheck && npm run build
```

키·주소는 환경변수 **경로**로만 다룹니다(`COURSESPEC_LLM_KEY_PATH`, `COURSESPEC_LLM_URL_PATH`,
`COURSESPEC_LLM_MODEL`). 값을 코드·로그·응답에 넣지 않습니다. 스텁 모드가 아니고 키 경로가
없으면 쉬운 한국어 안내를 돌려줍니다. 자세한 실행·테스트 방법은 [web/README.md](web/README.md).

## 관련 저장소

- [moodle-agent-mcp](https://github.com/scottnaddle/moodle-agent-mcp) — Moodle MCP 서버 (Moodle 퍼블리셔의 실행 대상)
- [moodle-local_ubionai](https://github.com/scottnaddle/moodle-local_ubionai) — MCP가 의존하는 Moodle 로컬 플러그인
- [THU-MAIC/OpenMAIC](https://github.com/THU-MAIC/OpenMAIC) — 멀티에이전트 인터랙티브 수업 생성 (수업 생성 대상)
- [HKUDS/DeepTutor](https://github.com/HKUDS/DeepTutor) — 학습자 튜터 (튜터 팩의 대상)
