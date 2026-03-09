from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.db import get_db
from app.db.model_definitions import DailyReport, DispatchTask
from app.schemas.common import build_response
from app.schemas.dispatch import (
    DailyReportDetail,
    ManualReportRunRequest,
    ManualReportRunResponse,
    ReportSectionDetail,
    SenderEventRequest,
    SenderHeartbeatRequest,
    SenderStatusDetail,
    SenderTaskResultRequest,
)
from app.security.auth import require_admin_token, require_sender_token
from app.services.dispatch_service import DispatchService, build_pending_task_payload
from app.services.scheduler_dispatch_flow import SchedulerDispatchFlow
from app.services.sender_events_service import record_sender_event
from app.services.sender_service import get_sender_health, upsert_sender_heartbeat

router = APIRouter(tags=["dispatch"])


@router.post("/admin/report/run")
def run_report_pipeline(
    payload: ManualReportRunRequest,
    _: str = Depends(require_admin_token),
    session=Depends(get_db),
) -> dict[str, object]:
    flow = SchedulerDispatchFlow(session)
    result = flow.run(
        report_date=payload.report_date,
        force_regenerate=payload.force_regenerate,
        skip_send=payload.skip_send,
    )
    session.commit()
    run_status = "completed"
    if result.report_reused and (payload.skip_send or result.dispatch_created_count == 0):
        run_status = "skipped"

    response = ManualReportRunResponse(
        job_id=result.job_id,
        status=run_status,
        report_date=result.report_generation.report.report_date,
        generation_status=result.report_generation.report.generation_status,
        fallback_used=result.report_generation.report.fallback_used,
        dispatch_task_ids=result.dispatch_task_ids,
        warnings=[*result.collection_warnings, *result.report_generation.warnings],
        last_error=result.report_generation.report.last_error,
    )
    return build_response(data=response.model_dump(mode="json"))


@router.get("/admin/reports/{report_date}")
def get_report_detail(
    report_date: date,
    _: str = Depends(require_admin_token),
    session=Depends(get_db),
) -> dict[str, object]:
    report = session.scalar(
        select(DailyReport)
        .options(selectinload(DailyReport.sections))
        .where(DailyReport.report_date == report_date)
    )
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    section_meta = report.link_bundle.get("sections", {}) if isinstance(report.link_bundle, dict) else {}
    sections = [
        ReportSectionDetail(
            section_key=section.section_key,
            title=section.title,
            content=section.content,
            message_chunks=section.message_chunks or [section.content],
            render_mode=(
                section_meta.get(section.section_key, {}).get("render_mode", "template")
                if isinstance(section_meta.get(section.section_key), dict)
                else "template"
            ),
        )
        for section in sorted(report.sections, key=lambda item: (item.sort_order, item.id))
    ]

    payload = DailyReportDetail(
        report_date=report.report_date,
        generation_status=report.generation_status,
        fallback_used=report.fallback_used,
        full_text=report.full_text,
        total_word_count=report.total_word_count,
        total_message_chunks=report.total_message_chunks,
        link_bundle=report.link_bundle or {},
        sections=sections,
        created_at=report.created_at,
        generated_at=report.generated_at,
        last_error=report.last_error,
    )
    return build_response(data=payload.model_dump(mode="json"))


@router.get("/admin/tasks/{task_id}")
def get_task_detail(
    task_id: str,
    _: str = Depends(require_admin_token),
    session=Depends(get_db),
) -> dict[str, object]:
    task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    return build_response(
        data={
            "task_id": task.task_id,
            "status": task.status,
            "retry_count": task.retry_count,
            "last_error": task.last_error,
            "sender_id": task.sender_id,
            "scheduled_at": task.scheduled_at.isoformat(),
            "sent_at": task.sent_at.isoformat() if task.sent_at else None,
        }
    )


@router.get("/admin/senders/{sender_id}/status")
def get_sender_status(
    sender_id: str,
    _: str = Depends(require_admin_token),
    session=Depends(get_db),
) -> dict[str, object]:
    sender, derived_status, is_healthy = get_sender_health(session, sender_id)
    if sender is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sender not found")

    payload = SenderStatusDetail(
        sender_id=sender.sender_id,
        status=derived_status,
        wechat_login_status=sender.wechat_login_status,
        last_heartbeat_at=sender.last_heartbeat_at,
        is_healthy=is_healthy,
    )
    return build_response(data=payload.model_dump(mode="json"))


@router.post("/sender/heartbeat")
def sender_heartbeat(
    payload: SenderHeartbeatRequest,
    _: str = Depends(require_sender_token),
    session=Depends(get_db),
) -> dict[str, object]:
    settings = get_settings()
    sender = upsert_sender_heartbeat(session, payload)
    session.commit()
    return build_response(
        data={
            "server_time": sender.last_heartbeat_at.isoformat() if sender.last_heartbeat_at else payload.timestamp.isoformat(),
            "next_heartbeat_in_seconds": settings.sender_next_heartbeat_seconds,
        }
    )


@router.get("/sender/tasks/pending")
def get_pending_tasks(
    sender_id: str = Query(...),
    limit: int = Query(default=1, ge=1, le=10),
    _: str = Depends(require_sender_token),
    session=Depends(get_db),
) -> dict[str, object]:
    tasks = DispatchService(session).fetch_pending_tasks(sender_id=sender_id, limit=limit)
    session.commit()
    return build_response(data={"tasks": [build_pending_task_payload(task) for task in tasks]})


@router.post("/sender/tasks/{task_id}/result")
def report_task_result(
    task_id: str,
    payload: SenderTaskResultRequest,
    _: str = Depends(require_sender_token),
    session=Depends(get_db),
) -> dict[str, object]:
    task = session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))
    if task is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    if task.status == "sent":
        return build_response(data={"task_status": task.status})
    if task.status not in {"dispatched", "sending"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Task status conflict")

    service = DispatchService(session)
    if task.status == "dispatched":
        service.mark_task_sending(task)

    update = service.update_task_result(
        task=task,
        sender_id=payload.sender_id,
        success=payload.success,
        result_status=payload.status,
        retryable=payload.retryable,
        sent_at=payload.sent_at,
        error_message=payload.error_message,
        detail=payload.detail,
    )
    session.commit()
    return build_response(data={"task_status": update.status})


@router.post("/sender/events")
def report_sender_event(
    payload: SenderEventRequest,
    _: str = Depends(require_sender_token),
    session=Depends(get_db),
) -> dict[str, object]:
    data = record_sender_event(session, payload)
    session.commit()
    return build_response(data=data)
