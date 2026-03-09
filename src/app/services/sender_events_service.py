from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.db.repositories import SystemEventRepository
from app.schemas.dispatch import SenderEventRequest
from app.services.sender_service import get_sender

logger = logging.getLogger(__name__)


def record_sender_event(session: Session, payload: SenderEventRequest) -> dict[str, object]:
    sender = get_sender(session, payload.sender_id)
    if sender is None:
        logger.warning(
            "Dropping sender event for unknown sender_id=%s event_type=%s",
            payload.sender_id,
            payload.event_type,
        )
        return build_sender_event_payload(payload)

    log_method = logger.error if payload.level == "error" else logger.warning if payload.level == "warning" else logger.info
    log_method(
        "Sender event sender_id=%s event_type=%s level=%s message=%s detail=%s",
        payload.sender_id,
        payload.event_type,
        payload.level,
        payload.message,
        payload.detail,
    )
    SystemEventRepository(session).create(
        event_type=payload.event_type,
        level=payload.level,
        object_type="sender",
        object_id=payload.sender_id,
        message=payload.message,
        detail=payload.detail,
        occurred_at=payload.occurred_at,
    )
    return build_sender_event_payload(payload)


def build_sender_event_payload(payload: SenderEventRequest) -> dict[str, object]:
    return {
        "sender_id": payload.sender_id,
        "event_type": payload.event_type,
        "level": payload.level,
        "message": payload.message,
        "detail": payload.detail,
        "occurred_at": payload.occurred_at.isoformat(),
    }
