from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from zoneinfo import ZoneInfo

from app.core.config import get_settings


@lru_cache(maxsize=8)
def get_timezone(timezone_name: str | None = None) -> ZoneInfo:
    return ZoneInfo(timezone_name or get_settings().timezone)


def now_in_timezone(timezone_name: str | None = None) -> datetime:
    return datetime.now(get_timezone(timezone_name))
