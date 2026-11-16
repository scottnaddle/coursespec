"""웹 UI 의 요청/응답 모델.

화면·API 는 구조화된 JSON 만 주고받고, 저장은 서버 쪽 작업 공간의 YAML 로 한다.
교수 화면에는 YAML·JSON Patch·도구 이름을 보여 주지 않는다.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Week(BaseModel):
    title: str
    summary: str = ""


class GradingItem(BaseModel):
    name: str
    weight: int


class Suggestion(BaseModel):
    id: str
    text: str
    target: str = ""
    status: Literal["pending", "accepted", "skipped"] = "pending"
    # 수락 시 본문에 반영하는 내부 규칙. 교수 화면에는 노출하지 않는다.
    apply: dict[str, Any] | None = None


class DraftUpdate(BaseModel):
    """교수가 화면 02 에서 편집한 필드. 주어진 필드만 바꾼다."""

    title: str | None = None
    intro: str | None = None
    outcomes: list[str] | None = None
    weeks: list[Week] | None = None
    grading: list[GradingItem] | None = None


class Draft(BaseModel):
    id: str
    title: str
    intro: str = ""
    goals: str = ""
    outcomes: list[str] = Field(default_factory=list)
    weeks: list[Week] = Field(default_factory=list)
    grading: list[GradingItem] = Field(default_factory=list)
    suggestions: list[Suggestion] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""
