"""실라버스 초안 생성.

이 모듈의 LLM 호출은 **실라버스 초안 필드 생성에만** 쓴다. 즉 제목, 한 줄 소개,
학습목표, 주차 제목·요약, 평가 항목·비중, 그리고 교수에게 보여 주는 제안(suggestions)을
만드는 일이다. LMS 실행(Moodle/Canvas/오픈마익), `coursespec plan` 적용, 설계서 확정,
배포에는 절대 쓰지 않는다. 실제 LMS 실행은 웹 UI에서 교수자가 승인한 뒤에만, 그리고
이 M1 에서는 구현하지 않는다.

키·주소는 **경로만** 다룬다. 파일 내용(값)은 로그·예외 메시지·응답·커밋에 넣지 않는다.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Callable

from .errors import DraftError

# 환경변수 이름: 값이 아니라 "값이 담긴 파일의 경로" 또는 모델 이름만 담는다.
ENV_STUB = "COURSESPEC_LLM_STUB"
ENV_KEY_PATH = "COURSESPEC_LLM_KEY_PATH"
ENV_URL_PATH = "COURSESPEC_LLM_URL_PATH"
ENV_MODEL = "COURSESPEC_LLM_MODEL"

MODEL_MISSING_MESSAGE = (
    "모델 연결 정보가 없습니다. 경로를 설정하거나 잠시 후 다시 시도해 주세요."
)

_SYSTEM_PROMPT = (
    "당신은 대학 교수를 돕는 강의계획서 작성 도우미입니다. "
    "입력(과목 이름, 목표, 참고 자료 텍스트)을 바탕으로 '실라버스 수준'의 강의계획서 초안을 만듭니다. "
    "이 출력은 초안 필드(제목, 한 줄 소개, 학습목표, 주차 제목·요약, 평가 항목·비중, 제안)에만 쓰이며, "
    "LMS 실행이나 설계서 확정·배포에는 쓰이지 않습니다. "
    "자료에 없는 내용을 지어낸 사실로 단정하지 말고, 불확실한 내용은 '제안'으로 표시하세요. "
    "자료에 있는 내용의 흔적(예: 특정 장이 특정 주차)은 초안이나 제안에 남기세요. "
    "반드시 아래 JSON 형식만 출력하고 다른 설명은 붙이지 마세요."
)


def build_messages(title: str, goals: str, sources: list[tuple[str, str]]) -> list[dict]:
    """모델에 보낼 대화 메시지를 만든다."""
    source_blocks = []
    for filename, text in sources:
        source_blocks.append(f"[자료: {filename}]\n{text}")
    user = [
        f"과목 이름: {title}",
        f"가르치고 싶은 점·목표: {goals or '(없음)'}",
        "",
    ]
    if source_blocks:
        user.append("참고 자료 (발췌):")
        user.extend(source_blocks)
    else:
        user.append("참고 자료: 없음. 과목 이름과 목표만으로 초안을 만드세요.")
    user.append(
        "\n다음 JSON 을 채워 주세요. weeks 는 3~6개, grading 은 가중치 합이 100 이 되게, "
        "suggestions 는 0~4개로, 각 제안은 id·text·target·apply(없으면 null)를 가집니다."
    )
    user.append(
        '형식: {"title": "...", "intro": "...", "outcomes": ["..."], '
        '"weeks": [{"title": "...", "summary": "..."}], '
        '"grading": [{"name": "...", "weight": 20}], '
        '"suggestions": [{"id": "s1", "text": "...", "target": "주차 3 제목", '
        '"apply": {"kind": "week_title", "index": 2, "value": "..."}}]}'
    )
    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": "\n".join(user)},
    ]


# --- 결정적 스텁 -------------------------------------------------------------

_WEEK_SEEDS = [
    ("핵심 개념 이해", "이 과정의 중심 개념과 배경을 살펴봅니다."),
    ("사례에 적용하기", "배운 개념을 실제 장면에 적용해 봅니다."),
    ("실습과 동료 피드백", "직접 만들어 보고 서로의 결과를 다듬습니다."),
    ("정리와 성찰", "배운 내용을 정리하고 다음 단계를 계획합니다."),
]


def _week_count(goals: str) -> int:
    match = re.search(r"(\d{1,2})\s*주(?:\s*차)?", goals or "")
    if match:
        count = int(match.group(1))
        return max(3, min(count, 8))
    return 4


def stub_payload(title: str, goals: str, sources: list[tuple[str, str]]) -> dict:
    """네트워크 없이 입력을 반영한 결정적 초안을 만든다.

    자료 키워드(예: '윤리')가 있으면 주차·학습목표·제안에 그 흔적이 남는다.
    """
    combined = (goals or "") + "\n" + "\n".join(text for _, text in sources)
    has_ethics = "윤리" in combined
    count = _week_count(goals)

    weeks = []
    for i in range(count):
        if i < len(_WEEK_SEEDS):
            week_title, week_summary = _WEEK_SEEDS[i]
        else:
            week_title, week_summary = f"심화와 적용 {i + 1}", "앞선 내용을 심화하고 적용합니다."
        weeks.append({"title": week_title, "summary": week_summary})

    if has_ethics and weeks:
        weeks[-1] = {
            "title": "윤리와 책임",
            "summary": "활용 과정의 윤리·개인정보 위험을 다루고, 책임 있는 활용을 성찰합니다.",
        }

    outcomes = [
        f"{title}의 핵심 개념과 용어를 설명할 수 있다.",
        "배운 개념을 실제 사례에 적용해 문제를 해결할 수 있다.",
        "자신의 맥락에 맞는 계획을 세우고 결과를 평가할 수 있다.",
    ]
    if has_ethics:
        outcomes[-1] = "활용 과정의 윤리·개인정보 위험을 평가하고 책임 있는 기준을 세울 수 있다."

    intro = f"{title}의 핵심 개념을 이해하고, 실제 사례에 적용하는 방법을 익히는 과정입니다."
    if goals:
        intro = f"{title}의 핵심을 다루며, 교수자가 바라는 방향({goals.strip()})에 맞춰 설계한 과정입니다."

    grading = [
        {"name": "퀴즈", "weight": 20},
        {"name": "토론", "weight": 20},
        {"name": "설계 과제", "weight": 60},
    ]

    suggestions = [
        {
            "id": "s1",
            "text": "3주차 제목을 '실습과 동료 피드백 다듬기'로 바꾸면, 서로의 결과를 고치는 단계가 더 분명해집니다.",
            "target": "주차 3 제목",
            "apply": {"kind": "week_title", "index": 2, "value": "실습과 동료 피드백 다듬기"},
        },
        {
            "id": "s2",
            "text": "퀴즈 비중을 10%로 낮추면 실습·설계 중심의 목표와 더 잘 맞습니다.",
            "target": "평가 비중",
            "apply": {"kind": "grading_weight", "index": 0, "value": 10},
        },
    ]
    if has_ethics:
        suggestions.append(
            {
                "id": "s3",
                "text": "올려 주신 자료의 '윤리' 내용은 마지막 주차에 반영했습니다. 다른 주차로 옮기고 싶으면 주차를 직접 수정하세요.",
                "target": "참고",
                "apply": None,
            }
        )

    return {
        "title": title,
        "intro": intro,
        "outcomes": outcomes,
        "weeks": weeks,
        "grading": grading,
        "suggestions": suggestions,
    }


# --- 실제 LLM 호출 (테스트·로컬 데모에서는 쓰지 않는다) -------------------------

def _read_secret_path(env_name: str) -> str | None:
    path = os.environ.get(env_name)
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError:
        return None


def _call_llm(title: str, goals: str, sources: list[tuple[str, str]]) -> dict:
    """키·주소 경로를 읽어 OpenAI 호환 채팅 API 를 호출한다. 값은 절대 로그에 남기지 않는다."""
    key = _read_secret_path(ENV_KEY_PATH)
    url = _read_secret_path(ENV_URL_PATH)
    if not key or not url:
        raise DraftError(MODEL_MISSING_MESSAGE)

    model = os.environ.get(ENV_MODEL) or None
    body: dict = {
        "messages": build_messages(title, goals, sources),
        "temperature": 0.4,
    }
    if model:
        body["model"] = model

    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise DraftError("초안을 만들지 못했습니다. 잠시 후 다시 시도해 주세요.") from exc
    except urllib.error.URLError as exc:
        raise DraftError("초안을 만들지 못했습니다. 연결을 확인하고 다시 시도해 주세요.") from exc

    try:
        data = json.loads(raw)
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise DraftError("초안을 만들지 못했습니다. 모델 응답을 읽지 못했습니다.") from exc

    return _parse_json_content(content)


def _parse_json_content(content: str) -> dict:
    """모델 응답에서 JSON 만 뽑아낸다. 코드 펜스를 벗겨내고 안전하게 파싱한다."""
    text = content.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise DraftError("초안을 만들지 못했습니다. 모델 응답이 JSON 이 아닙니다.")
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise DraftError("초안을 만들지 못했습니다. 모델 응답을 읽지 못했습니다.") from exc
    if not isinstance(payload, dict):
        raise DraftError("초안을 만들지 못했습니다. 모델 응답 형식이 올바르지 않습니다.")
    return payload


# --- 진입점 -------------------------------------------------------------------

def generate_draft(
    title: str,
    goals: str = "",
    sources: list[tuple[str, str]] | None = None,
    call: Callable[[str, str, list[tuple[str, str]]], dict] | None = None,
) -> dict:
    """초안 필드 JSON(dict)을 만든다.

    - `call` 이 주어지면 `call(title, goals, sources)` 로 결과 dict 를 받는다 (테스트 주입).
    - `COURSESPEC_LLM_STUB=1` 이면 결정적 스텁을 쓴다 (테스트·로컬 데모).
    - 둘 다 아니면 키·주소 경로를 읽어 실제 호출을 시도한다.
    """
    sources = list(sources or [])
    if call is not None:
        return call(title, goals, sources)
    if os.environ.get(ENV_STUB) == "1":
        return stub_payload(title, goals, sources)
    return _call_llm(title, goals, sources)
