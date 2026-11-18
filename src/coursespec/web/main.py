"""개발용 진입점: `python -m coursespec.web.main` 으로 백엔드를 띄운다.

포트는 `COURSESPEC_WEB_PORT`(기본 18080)를 쓴다. 스텁 모드(`COURSESPEC_LLM_STUB=1`)로
뜨면 네트워크 LLM 호출 없이 초안을 만들 수 있다.
"""

from __future__ import annotations

import os

import uvicorn

from .app import app


def main() -> None:
    port = int(os.environ.get("COURSESPEC_WEB_PORT", "18080"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
