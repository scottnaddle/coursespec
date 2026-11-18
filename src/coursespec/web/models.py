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


# --- M2: 과정 지도 ------------------------------------------------------------

class EditAction(BaseModel):
    """화면 편집 동작 하나. 서버가 검증된 패치로 바꿔 적용한다."""

    action: Literal["update_unit", "update_item", "add_item", "remove_item", "move_item"]
    unit_id: str | None = None
    item_id: str | None = None
    to_unit_id: str | None = None
    kind: str | None = None  # 활동 추가용 한국어 유형 (읽기·퀴즈·과제…)
    title: str | None = None
    summary: str | None = None
    minutes: int | None = None
    due_day: int | None = None  # 명시하면 변경, None 이면 마감일 삭제


class EditRequest(BaseModel):
    actions: list[EditAction]


class ChangeRequestBody(BaseModel):
    text: str = Field(min_length=1)
