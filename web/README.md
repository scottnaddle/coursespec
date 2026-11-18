# CourseSpec 교수용 웹 UI (프론트엔드)

Vite + React + TypeScript 프론트엔드. 목업 화면 01(새 과정 시작)·02(강의계획서 초안 검토)와
앱 셸(사이드바·상단바)을 구현합니다. 기본 화면에 YAML·JSON Patch·도구 이름을 보여 주지 않습니다.

## 실행

Node는 사용자 영역 Node(예: `../.tools/node`)를 씁니다. 시스템 기본 Node(v10)는 쓰지 않습니다.

```bash
# 의존성 설치
npm install

# 개발 서버 (프론트 15180, /api 를 백엔드 18080 으로 프록시)
npm run dev

# 백엔드를 스텁 모드로 띄운 뒤 (다른 터미널)
COURSESPEC_LLM_STUB=1 COURSESPEC_WEB_PORT=18080 python -m coursespec.web.main
```

백엔드 실행·설치 방법은 저장소 루트 `README.md`의 웹 UI 항목을 참고하세요.
비밀값은 경로로만 다루며, 실주소·키를 이 문서나 코드에 적지 않습니다.

## 테스트·검사

```bash
npm test          # Vitest + Testing Library
npm run lint      # ESLint
npm run typecheck # tsc --noEmit
npm run build     # 프로덕션 빌드 (web/dist)
```

프론트 테스트는 API 를 mock 하므로 네트워크·모델을 호출하지 않습니다.
백엔드가 `web/dist` 를 감지하면 정적 빌드를 함께 서빙합니다(개발 시에는 Vite 프록시 사용).
