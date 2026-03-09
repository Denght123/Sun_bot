from __future__ import annotations

import logging
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import get_settings
from app.core.time import get_timezone
from app.db import get_session_factory
from app.services.scheduler_dispatch_flow import SchedulerDispatchFlow

SCHEDULER_SERVICE_NAME = "scheduler-service"
logger = logging.getLogger(__name__)


def run_daily_dispatch_job(report_date: date | None = None, skip_send: bool = False) -> None:
    session = get_session_factory()()
    try:
        result = SchedulerDispatchFlow(session).run(report_date=report_date, skip_send=skip_send)
        session.commit()
    except Exception:
        session.rollback()
        logger.exception(
            "Scheduler dispatch job failed",
            extra={"report_date": report_date.isoformat() if report_date else None},
        )
        raise
    finally:
        session.close()

    logger.info(
        "Scheduler dispatch job completed",
        extra={
            "job_id": result.job_id,
            "report_date": result.report_generation.report.report_date.isoformat(),
            "generation_status": result.report_generation.report.generation_status,
            "dispatch_task_ids": result.dispatch_task_ids,
            "warnings": [*result.collection_warnings, *result.report_generation.warnings],
        },
    )


def build_scheduler() -> BackgroundScheduler:
    settings = get_settings()
    timezone = get_timezone(settings.effective_scheduler_timezone)
    scheduler = BackgroundScheduler(timezone=timezone)
    scheduler.add_job(
        run_daily_dispatch_job,
        trigger=CronTrigger(
            hour=settings.daily_dispatch_hour,
            minute=settings.daily_dispatch_minute,
            timezone=timezone,
        ),
        id="daily_report_dispatch",
        replace_existing=True,
    )
    return scheduler


def start_scheduler() -> BackgroundScheduler | None:
    settings = get_settings()
    if not settings.scheduler_enabled:
        logger.info("Scheduler disabled by configuration")
        return None
    scheduler = build_scheduler()
    scheduler.start()
    logger.info("Scheduler started", extra={"timezone": settings.effective_scheduler_timezone})
    return scheduler
