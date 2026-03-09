from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.time import now_in_timezone
from app.core.time_window import default_report_date
from app.services.collection_pipeline import run_collection_pipeline
from app.services.dispatch_service import DispatchService
from app.services.report_service import ReportGenerationResult, ReportGeneratorService


@dataclass(slots=True)
class SchedulerRunResult:
    job_id: str
    report_generation: ReportGenerationResult
    dispatch_task_ids: list[str]
    collection_warnings: list[str]
    report_reused: bool
    dispatch_created_count: int
    dispatch_reused_count: int


class SchedulerDispatchFlow:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.report_service = ReportGeneratorService(session)
        self.dispatch_service = DispatchService(session)

    def run(
        self,
        *,
        report_date: date | None = None,
        force_regenerate: bool = False,
        skip_send: bool = False,
    ) -> SchedulerRunResult:
        target_date = report_date or default_report_date(self.report_service.settings.timezone)
        existing_report = self.report_service.find_existing(target_date)
        report_reused = existing_report is not None and not force_regenerate and existing_report.generation_status in {"success", "fallback_success"}
        should_run_collection = force_regenerate or existing_report is None or existing_report.generation_status not in {"success", "fallback_success"}
        collection_warnings: list[str] = []

        if should_run_collection:
            collection_result = run_collection_pipeline(session=self.session, report_date=target_date)
            collection_warnings = collection_result.warnings

        report_generation = self.report_service.get_or_generate(target_date, force_regenerate=force_regenerate)

        dispatch_task_ids: list[str] = []
        dispatch_created_count = 0
        dispatch_reused_count = 0
        if not skip_send and report_generation.report.generation_status in {"success", "fallback_success"}:
            payload = dict(report_generation.report.link_bundle or {})
            payload.setdefault("message_chunks", self.report_service.build_message_chunks(report_generation.report))
            payload.setdefault("full_text", report_generation.report.full_text)
            payload.setdefault("generated_at", report_generation.report.generated_at.isoformat() if report_generation.report.generated_at else now_in_timezone().isoformat())
            dispatch_result = self.dispatch_service.create_daily_report_task(
                report_id=report_generation.report.id,
                report_date=target_date,
                payload=payload,
                force_recreate=force_regenerate,
            )
            dispatch_task_ids = dispatch_result.task_ids
            dispatch_created_count = dispatch_result.created_count
            dispatch_reused_count = dispatch_result.reused_count

        return SchedulerRunResult(
            job_id=f"job_report_run_{target_date.strftime('%Y%m%d')}_{uuid4().hex[:6]}",
            report_generation=report_generation,
            dispatch_task_ids=dispatch_task_ids,
            collection_warnings=collection_warnings,
            report_reused=report_reused,
            dispatch_created_count=dispatch_created_count,
            dispatch_reused_count=dispatch_reused_count,
        )
