from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class ReportWindow:
    report_date: date
    start: datetime
    end: datetime


def get_timezone(timezone_name: str) -> ZoneInfo:
    return ZoneInfo(timezone_name)


def default_report_date(timezone_name: str) -> date:
    return datetime.now(get_timezone(timezone_name)).date()


def build_report_window(report_date: date, timezone_name: str) -> ReportWindow:
    timezone = get_timezone(timezone_name)
    previous_day = report_date - timedelta(days=1)
    start = datetime.combine(previous_day, time(hour=18, minute=0), tzinfo=timezone)
    end = datetime.combine(report_date, time(hour=7, minute=30), tzinfo=timezone)
    return ReportWindow(report_date=report_date, start=start, end=end)


def is_in_window(timestamp: datetime | None, window: ReportWindow) -> bool:
    if timestamp is None:
        return False
    return window.start <= timestamp <= window.end
