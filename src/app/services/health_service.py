from __future__ import annotations

from app.core.config import get_settings
from app.schemas.health import DependencyStatus, LiveStatus, ReadinessStatus
from app.db.session import ping_database
from app.cache.redis import ping_redis

API_SERVICE_NAME = "api-service"


def build_live_status() -> LiveStatus:
    settings = get_settings()
    return LiveStatus(
        status="ok",
        service=API_SERVICE_NAME,
        environment=settings.app_env,
        timezone=settings.timezone,
    )


def build_readiness_status() -> tuple[ReadinessStatus, bool]:
    settings = get_settings()
    database_ok, database_detail = ping_database()
    redis_ok, redis_detail = ping_redis()
    ready = database_ok and redis_ok
    status = "ok" if ready else "degraded"

    payload = ReadinessStatus(
        status=status,
        service=API_SERVICE_NAME,
        environment=settings.app_env,
        timezone=settings.timezone,
        database=DependencyStatus(ok=database_ok, detail=database_detail),
        redis=DependencyStatus(ok=redis_ok, detail=redis_detail),
    )
    return payload, ready
