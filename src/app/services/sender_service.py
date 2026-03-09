from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import get_timezone, now_in_timezone
from app.db.model_definitions import Sender
from app.db.repositories import SenderRepository
from app.schemas.dispatch import SenderHeartbeatRequest

SenderHealthStatus = Literal["online", "offline", "degraded"]


def derive_sender_health(last_heartbeat_at: datetime | None, now: datetime | None = None) -> SenderHealthStatus:
    if last_heartbeat_at is None:
        return "offline"

    settings = get_settings()
    online_threshold = timedelta(seconds=settings.sender_online_threshold_seconds)
    degraded_threshold = timedelta(seconds=settings.sender_degraded_threshold_seconds)
    reference_time = now or now_in_timezone()
    heartbeat_time = last_heartbeat_at
    if heartbeat_time.tzinfo is None:
        heartbeat_time = heartbeat_time.replace(tzinfo=get_timezone(settings.timezone))
    if reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=get_timezone(settings.timezone))
    heartbeat_age = reference_time - heartbeat_time
    if heartbeat_age <= online_threshold:
        return "online"
    if heartbeat_age <= degraded_threshold:
        return "degraded"
    return "offline"


def upsert_sender_heartbeat(session: Session, payload: SenderHeartbeatRequest) -> Sender:
    return SenderRepository(session).upsert_heartbeat(
        sender_id=payload.sender_id,
        status=payload.status,
        wechat_login_status=payload.wechat_login_status,
        reported_at=payload.timestamp,
        client_version=payload.client_version,
        host_name=payload.host_name,
        current_ip=payload.ip,
        payload=payload.model_dump(mode="json"),
    )


def get_sender(session: Session, sender_id: str) -> Sender | None:
    return SenderRepository(session).get_by_business_id(sender_id)


def get_sender_health(session: Session, sender_id: str, now: datetime | None = None) -> tuple[Sender | None, SenderHealthStatus, bool]:
    sender = get_sender(session, sender_id)
    if sender is None:
        return None, "offline", False

    derived_status = derive_sender_health(sender.last_heartbeat_at, now=now)
    is_healthy = derived_status == "online" and sender.wechat_login_status == "logged_in"
    return sender, derived_status, is_healthy
