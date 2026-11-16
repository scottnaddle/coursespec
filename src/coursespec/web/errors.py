"""웹 UI 전용 예외.

교수자에게 보여 주는 메시지는 항상 한국어이고, 원인과 다음 행동을 담는다.
예외를 밖으로 흘려보내면 FastAPI 핸들러가 500 토막 스택 대신 깔끔한 JSON 으로 바꾼다.
"""

from __future__ import annotations


class WebError(Exception):
    """교수자에게 한국어 메시지로 안내되는 요청 오류."""

    def __init__(self, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


class ExtractionError(Exception):
    """자료 파일 하나를 읽지 못했을 때. 파일별로 보고하고 다른 파일로 계속한다."""

    def __init__(self, filename: str, message: str) -> None:
        super().__init__(f"{filename}: {message}")
        self.filename = filename
        self.message = message


class DraftError(Exception):
    """초안 생성 실패(모델 연결 정보 없음 등). 교수자에게 안내할 한국어 메시지를 담는다."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
