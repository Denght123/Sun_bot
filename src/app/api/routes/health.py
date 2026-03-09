from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.schemas.common import build_response
from app.services.health_service import build_live_status, build_readiness_status

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def live() -> dict[str, object]:
    payload = build_live_status()
    return build_response(data=payload.model_dump())


@router.get("/ready")
def ready() -> JSONResponse:
    payload, is_ready = build_readiness_status()
    response = build_response(data=payload.model_dump())
    status_code = 200 if is_ready else 503
    return JSONResponse(status_code=status_code, content=response)
