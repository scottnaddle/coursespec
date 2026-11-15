# 설계서 작성 안내 (v0.2)

정식 정의는 [schema/coursespec.schema.json](../schema/coursespec.schema.json)이고, 이 문서는 사람과 설계 에이전트가 읽는 안내입니다. YAML과 JSON 모두 됩니다.

## 최상위

| 필드 | 필수 | 설명 |
|---|---|---|
| `coursespec` | ✓ | 스펙 버전. `"0.2"` (0.1 설계서도 그대로 유효) |
| `id` | ✓ | 설계서 영구 id (소문자·숫자·하이픈, 63자 이하). 바꾸면 재배포 매칭이 끊깁니다 |
| `title` | ✓ | 과정명 |
| `version` | | 설계서 자체의 버전 (예: `0.3.0`) |
| `shortname` | | LMS 단축명. 없으면 `id` |
| `summary` | | 과정 소개 (마크다운) |
| `language`, `timezone` | | 기본 `ko`, `Asia/Seoul`. 날짜 변환에 시간대를 씁니다 |
| `outcomes` | | 학습목표 목록. `level`은 블룸 개정 분류 (remember … create) |
| `materials` | | 자료 매니페스트 (아래) |
| `grading` | | `aggregation`(weighted_mean·natural·mean)과 `categories`(id, name, weight%) |
| `policies.workload.max_minutes_per_unit` | | 단원별 예상 학습시간 상한. 넘으면 린트 경고 |
| `units` | ✓ | 단원(주차) 목록 |
| `badges` | | 활동 완료·과정 성적 기준 배지 |
| `extensions` | | LMS 전용 설정 (`moodle`, `canvas`) |

## 자료 매니페스트 (`materials[]`)

```yaml
materials:
  - id: m-ethics
    title: 교실 속 AI 윤리와 학생 데이터 보호 지침
    kind: document            # document·slides·video·audio·web·dataset·other
    source: materials/ai-ethics-guide.pdf   # 설계서 기준 상대 경로 또는 URL
    units: [w4]
    outcomes: [lo3]
    uses: [generation, tutor, learner]
    rights: {owner: Scott, license: cc-by-4.0}
    sha256: …                 # 선택: 자료 버전 고정
```

`uses`는 이 자료를 어디에 써도 되는지에 대한 교수자의 선언입니다. `generation`은 OpenMAIC 같은 콘텐츠 생성의 입력, `tutor`는 튜터 지식베이스, `learner`는 학습자에게 파일로 배포해도 된다는 뜻입니다. 학생 개인정보가 담긴 자료는 넣지 않습니다. 연동 방식은 [integration.md](integration.md)를 보세요.

## 단원 (`units[]`)

`id`, `title`, `items`가 필수입니다. `summary`, `opens_day`(공개일), `requires`(이 단원을 열기 위해 완료해야 할 활동 id)를 쓸 수 있습니다.

## 활동 (`items[]`) 공통 필드

| 필드 | 설명 |
|---|---|
| `id`, `type`, `title` | 필수. id는 설계서 전체(단원·활동·목표·카테고리·배지)에서 유일 |
| `intro` | 활동 설명 (마크다운) |
| `outcomes` | 연결된 학습목표 id. 린트의 정렬 점검에 쓰입니다 |
| `estimated_minutes` | 예상 학습시간 |
| `visible` | 기본 true |
| `opens_day` / `due_day` / `cutoff_day` | 공개일 / 마감일(그날 23:59) / 최종 마감일 |
| `requires` | 먼저 완료해야 할 활동 id |
| `completion` | `mode`: none · manual · view · submit · grade · pass(`pass_grade`) · posts(`posts`) |
| `grading` | `max`(만점)와 `category`(성적 카테고리 id). 있으면 "평가 활동"으로 봅니다 |
| `extensions` | 예: `extensions.moodle.settings`는 Moodle 모듈 필드로 그대로 전달 |

## 유형별 필드

| 유형 | 필드 |
|---|---|
| `page` | `content`(필수), `content_format`(markdown·html), `video_url` |
| `file` | `source`(URL 또는 워크스페이스 경로) 또는 `material`(자료 id), `filename` |
| `assignment` | `submission.types`(text·file), `submission.max_files`, `rubric` |
| `quiz` | `quiz.time_limit_minutes`, `quiz.attempts`(0=무제한), `quiz.grade_method`, `questions` |
| `discussion` | `discussion.style`(general·qanda) |
| `peer_review` | `submission`, `rubric`, `peer_review.assessment_max`, `peer_review.assessment_due_day` |
| `wiki` | `wiki.mode`(collaborative·individual) |
| `glossary` | — |
| `survey` | `survey.anonymous` |
| `h5p` | `source`(필수), `filename` |
| `interactive_lecture` | `lecture` (아래) |

### 인터랙티브 강의 (`lecture`)

```yaml
lecture:
  engine: openmaic
  prompt: 학생 데이터와 AI 에이전트, 교사가 지켜야 할 다섯 가지 원칙을 사례 중심으로 설명
  materials: [m-ethics, m-scenarios]   # 생성에 쓸 자료
  min_progress: 80                     # 완료 기준 진행률 %
  classroom:                           # 생성 후 기록 (plan --target openmaic 실행 결과)
    id: stg_42
    server: ubion-maic
    archive: lectures/w4-lecture.stage.json
  exports:                             # 상호작용 수업을 못 싣는 LMS용 대체 산출물
    html: lectures/w4-lecture.html
    video: lectures/w4-lecture.mp4
```

`prompt`나 `classroom` 중 하나는 있어야 합니다. `classroom`은 손으로 쓰기보다 생성 계획의 마지막 단계(검증된 패치)가 채우게 두세요.

### 문항 (`questions[]`)

| type | 필드 |
|---|---|
| `multichoice` | `choices[]`(text, correct, feedback), `multiple`(복수 정답) |
| `truefalse` | `answer`(true/false) |
| `shortanswer` | `accepted_answers[]`, `case_sensitive` |
| `essay` | `grader_info` |

공통으로 `text`(필수), `name`, `mark`(배점, 기본 1), `feedback`, `outcomes`를 씁니다.

### 루브릭

```yaml
rubric:
  name: 시나리오 루브릭
  criteria:
    - description: 학습목표와의 정렬
      levels:
        - { definition: 목표와 무관, score: 0 }
        - { definition: 명확히 정렬, score: 40 }
```

기준마다 수준이 2개 이상이고 점수가 겹치지 않아야 합니다. Moodle 워크숍 루브릭은 정수 점수만 받습니다.

## 린트 코드

| 코드 | 내용 |
|---|---|
| E001 | 중복 id |
| E002 | 정의되지 않은 학습목표 참조 |
| E003 | 없는 활동을 requires로 참조 |
| E004 | 선수조건 순환 |
| E005 | 정의되지 않은 성적 카테고리 |
| E006 | 배지 조건에 없는 활동 |
| E007 | 날짜 순서 오류 (마감 < 공개 등) |
| E008 | grade·pass 완료 조건에 grading 없음, pass_grade 누락·초과 |
| E009 | 문항 오류 (보기 부족, 정답 없음 등) |
| E010 | 루브릭 수준 점수 중복 |
| E011 | 유형에 맞지 않는 완료 조건 (submit, posts) |
| E012 | 설계서 id + 활동 id 가 LMS ID number(100자)를 넘음 |
| E013 | 가중 집계인데 카테고리 weight 없음 |
| E014 | 인터랙티브 강의에 `prompt` 도 `classroom` 도 없음 |
| E015 | 자료 매니페스트에 없는 자료 참조 |
| E016 | 자료가 없는 단원을 참조 |
| E017 | 학습자 배포가 허용되지 않은 자료(`uses`에 learner 없음)를 file 로 배포 |
| W101 | 다루지만 평가하지 않는 학습목표 |
| W102 | 어떤 활동도 다루지 않는 학습목표 |
| W103 | 학습목표와 연결되지 않은 평가 활동 |
| W104 | 카테고리 가중치 합이 100이 아님 |
| W105 | 단원 학습시간 상한 초과 |
| W106 | 같은/뒤 단원 활동을 선수조건으로 참조 |
| W107 | 문항 없는 퀴즈 |
| W108 | 배지 조건 활동에 완료 조건 없음 |
| W109 | 카테고리가 있는데 평가 활동에 카테고리 미지정 |
| W110 | 배포되지 않는 루브릭 (assignment·peer_review 외) |
| W111 | 생성용(`generation`)으로 표시되지 않은 자료를 강의 생성에 사용 |
| W112 | 용도가 있는 자료의 이용 권리(`rights.license`) 미확인 |
| W113 | 튜터용 자료가 하나도 연결되지 않은 학습목표 |
| W115 | 생성된 수업의 스냅샷(`classroom.archive`) 없음 |

## 설계서 고치기: 검증된 JSON Patch

설계 에이전트는 설계서를 통째로 다시 쓰지 않고 RFC 6902 패치(add·replace·remove·test)로 고칩니다.

```bash
echo '[{"op":"replace","path":"/units/0/title","value":"1주차 — 에이전트 입문"}]' \
  | coursespec patch course.yaml -          # --dry-run 으로 검증만
```

패치 결과가 스키마와 린트(오류 E)를 모두 통과해야만 파일에 쓰이고, 실패하면 파일은 그대로입니다. YAML 주석과 순서는 보존됩니다. 흐름 표기(`{a: b}`)는 중괄호 안쪽 공백 없이 쓰면 패치 전후 diff가 깔끔합니다.

## 설계 에이전트를 위한 메모

- 설계서를 수정할 때는 **id를 바꾸지 말고** 제목·내용만 바꾸세요. 새 활동에는 새 id를 주세요.
- 수정은 `coursespec patch` 로 하세요. 활동의 JSON Pointer 는 `/units/<단원 순서>/items/<활동 순서>` 입니다. 다른 사람이 동시에 고칠 수 있으면 `test` 연산으로 기대값을 먼저 확인하세요.
- 변경 후에는 항상 `coursespec lint`를 돌리고, 오류(E)는 고친 뒤 교수자에게 보여 주세요. 경고(W)는 교수자 판단으로 남겨도 됩니다.
- 학생 이름·성적 등 개인정보를 설계서에 쓰지 마세요.
