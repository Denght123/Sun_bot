from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ResponseEnvelope(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any = None


def build_response(data: Any = None, message: str = "ok", code: int = 0) -> dict[str, Any]:
    return ResponseEnvelope(code=code, message=message, data=data).model_dump()
