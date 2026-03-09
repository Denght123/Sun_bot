from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.db import get_db
from app.schemas.common import build_response
from app.security.auth import require_sender_token
from app.services.report_service import ReportGeneratorService

router = APIRouter(prefix="/content", tags=["content"])


@router.get("/menu")
def get_content_menu(
    keyword: str = Query(..., min_length=1),
    report_date: date | None = Query(default=None),
    _: str = Depends(require_sender_token),
    session=Depends(get_db),
) -> dict[str, object]:
    service = ReportGeneratorService(session)
    target_date = report_date or date.today()
    payload = service.build_keyword_payload(report_date=target_date, keyword=keyword)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Content not found")
    return build_response(data=payload)
