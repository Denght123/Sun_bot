from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import get_timezone, now_in_timezone
from app.db.model_definitions import DispatchTask, build_message_chunks_from_payload
from app.db.repositories import DispatchTaskRepository, SenderRepository, SystemEventRepository
from app.services.sender_service import get_sender_health

DEFAULT_TARGET_USER = None
DEFAULT_TASK_TYPE = "daily_report"


@dataclass(slots=True)
class DispatchCreationResult:
    task_ids: list[str]
    created_count: int
    reused_count: int


@dataclass(slots=True)
class TaskResultUpdate:
    task: DispatchTask
    status: str


class DispatchService:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = get_settings()
        self.tasks = DispatchTaskRepository(session)
        self.senders = SenderRepository(session)
        self.system_events = SystemEventRepository(session)

    def create_daily_report_task(
        self,
        *,
        report_id: int,
        report_date: date,
        payload: dict[str, object],
        sender_id: str | None = None,
        task_type: str = DEFAULT_TASK_TYPE,
        target_user: str | None = DEFAULT_TARGET_USER,
        force_recreate: bool = False,
    ) -> DispatchCreationResult:
        existing = self.tasks.find_active_by_report(report_id=report_id, task_type=task_type)
        if existing and not force_recreate:
            return DispatchCreationResult(task_ids=[task.task_id for task in existing], created_count=0, reused_count=len(existing))

        healthy_sender_id = self._resolve_sender_id(sender_id)
        status = "pending" if healthy_sender_id else "waiting_sender"
        task = self.tasks.create(
            task_id=self._build_task_id(report_date),
            report_id=report_id,
            sender_id=healthy_sender_id or sender_id,
            target_user=target_user or self.settings.dispatch_default_target_user,
            task_type=task_type,
            payload=payload,
            status=status,
            retry_count=0,
            max_retry=self.settings.dispatch_max_retry,
            scheduled_at=self._scheduled_time(report_date),
        )
        return DispatchCreationResult(task_ids=[task.task_id], created_count=1, reused_count=0)

    def recover_stale_tasks(self, *, now: datetime | None = None) -> list[DispatchTask]:
        reference_time = now or now_in_timezone()
        stale_before = reference_time - timedelta(seconds=self.settings.dispatch_stale_timeout_seconds)
        tasks = self.tasks.release_stale_tasks(stale_before=stale_before)
        for task in tasks:
            previous_status = task.status
            previous_sender_id = task.sender_id
            started_at = task.dispatched_at

            task.retry_count += 1
            retryable = task.retry_count < task.max_retry
            task.sender_id = None
            task.dispatched_at = None
            task.sent_at = None
            task.last_error = "dispatch_timeout_recovered"
            task.status = "pending" if retryable else "failed"

            self.tasks.create_attempt(
                dispatch_task_id=task.id,
                attempt_no=task.retry_count,
                sender_id=previous_sender_id,
                status="failed",
                error_code="dispatch_timeout",
                error_message=task.last_error,
                retryable=retryable,
                started_at=started_at,
                finished_at=reference_time,
            )
            self._record_dispatch_event(
                event_type="dispatch_timeout_recovered",
                level="warning" if retryable else "error",
                task=task,
                message=(
                    "Recovered stale dispatch task after sender timeout"
                    if retryable
                    else "Dispatch task failed after sender timeout reached retry limit"
                ),
                detail=self._build_task_event_detail(
                    task=task,
                    sender_id=previous_sender_id,
                    result_status="failed",
                    error_code="dispatch_timeout",
                    error_message=task.last_error,
                    retryable=retryable,
                    extra={
                        "previous_status": previous_status,
                        "recovered_at": reference_time.isoformat(),
                        "stale_before": stale_before.isoformat(),
                    },
                ),
                occurred_at=reference_time,
            )
        self.session.flush()
        return tasks

    def fetch_pending_tasks(self, *, sender_id: str, limit: int = 1) -> list[DispatchTask]:
        self.recover_stale_tasks()
        sender, _, is_healthy = get_sender_health(self.session, sender_id)
        if sender is None or not is_healthy:
            return []

        tasks = self.tasks.list_pending_for_sender(sender_id=sender_id, limit=limit)
        dispatched_at = now_in_timezone()
        for task in tasks:
            task.sender_id = sender_id
            task.status = "dispatched"
            task.dispatched_at = dispatched_at
        self.session.flush()
        return tasks

    def update_task_result(
        self,
        *,
        task: DispatchTask,
        sender_id: str,
        success: bool,
        result_status: str,
        retryable: bool,
        sent_at: datetime,
        error_message: str | None,
        detail: dict[str, object] | None = None,
    ) -> TaskResultUpdate:
        callback_detail = dict(detail or {})
        is_partial = result_status == "partial"
        attempt_success = success and result_status == "sent"
        effective_retryable = retryable and not is_partial
        error_code = self._extract_error_code(callback_detail)

        task.sender_id = sender_id
        task.sent_at = sent_at if attempt_success else None
        task.last_error = None if attempt_success else error_message

        self.tasks.create_attempt(
            dispatch_task_id=task.id,
            attempt_no=task.retry_count + 1,
            sender_id=sender_id,
            status="success" if attempt_success else "failed",
            error_code=None if attempt_success else error_code,
            error_message=error_message,
            retryable=effective_retryable,
            started_at=task.dispatched_at,
            finished_at=sent_at,
        )

        if attempt_success:
            task.status = "sent"
            task.dispatched_at = task.dispatched_at or sent_at
            self.session.flush()
            return TaskResultUpdate(task=task, status=task.status)

        task.retry_count += 1
        if effective_retryable and task.retry_count < task.max_retry:
            _, _, is_healthy = get_sender_health(self.session, sender_id, now=sent_at)
            task.status = "pending" if is_healthy else "waiting_sender"
            task.sender_id = sender_id if is_healthy else None
            task.sent_at = None
            task.dispatched_at = None
            if not is_healthy:
                self._record_dispatch_event(
                    event_type="dispatch_waiting_sender",
                    level="warning",
                    task=task,
                    message=error_message or "Retryable dispatch failure is waiting for a healthy sender",
                    detail=self._build_task_event_detail(
                        task=task,
                        sender_id=sender_id,
                        result_status=result_status,
                        error_code=error_code,
                        error_message=error_message,
                        retryable=effective_retryable,
                        callback_detail=callback_detail,
                    ),
                    occurred_at=sent_at,
                )
        else:
            task.status = "failed"
            task.sent_at = None
            task.dispatched_at = None
            task.sender_id = None
            if is_partial:
                self._record_dispatch_event(
                    event_type="dispatch_partial_send",
                    level="warning",
                    task=task,
                    message=error_message or "Sender reported partial send; task marked failed",
                    detail=self._build_task_event_detail(
                        task=task,
                        sender_id=sender_id,
                        result_status=result_status,
                        error_code=error_code,
                        error_message=error_message,
                        retryable=effective_retryable,
                        callback_detail=callback_detail,
                    ),
                    occurred_at=sent_at,
                )
            else:
                self._record_dispatch_event(
                    event_type="dispatch_task_failed",
                    level="error",
                    task=task,
                    message=error_message or "Dispatch task failed",
                    detail=self._build_task_event_detail(
                        task=task,
                        sender_id=sender_id,
                        result_status=result_status,
                        error_code=error_code,
                        error_message=error_message,
                        retryable=effective_retryable,
                        callback_detail=callback_detail,
                    ),
                    occurred_at=sent_at,
                )
        self.session.flush()
        return TaskResultUpdate(task=task, status=task.status)

    def mark_task_sending(self, task: DispatchTask) -> DispatchTask:
        task.status = "sending"
        task.dispatched_at = task.dispatched_at or now_in_timezone()
        self.session.flush()
        return task

    def _resolve_sender_id(self, sender_id: str | None) -> str | None:
        if sender_id:
            sender, _, is_healthy = get_sender_health(self.session, sender_id)
            return sender.sender_id if sender is not None and is_healthy else None

        for sender in self.senders.list_by_last_heartbeat():
            _, _, is_healthy = get_sender_health(self.session, sender.sender_id)
            if is_healthy:
                return sender.sender_id
        return None

    def _build_task_id(self, report_date: date) -> str:
        return f"task_{report_date.strftime('%Y%m%d')}_{uuid4().hex[:8]}"

    def _scheduled_time(self, report_date: date) -> datetime:
        timezone = get_timezone(self.settings.timezone)
        return datetime.combine(report_date, time(hour=8, minute=0), tzinfo=timezone)

    def _extract_error_code(self, detail: dict[str, object]) -> str | None:
        error_code = detail.get("error_code")
        if error_code is None:
            return None
        if isinstance(error_code, str):
            return error_code or None
        return str(error_code)

    def _record_dispatch_event(
        self,
        *,
        event_type: str,
        level: str,
        task: DispatchTask,
        message: str,
        detail: dict[str, Any],
        occurred_at: datetime,
    ) -> None:
        self.system_events.create(
            event_type=event_type,
            level=level,
            object_type="dispatch_task",
            object_id=task.task_id,
            message=message,
            detail=detail,
            occurred_at=occurred_at,
        )

    def _build_task_event_detail(
        self,
        *,
        task: DispatchTask,
        sender_id: str | None,
        result_status: str,
        error_code: str | None,
        error_message: str | None,
        retryable: bool,
        callback_detail: dict[str, object] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        detail: dict[str, Any] = {
            "task_id": task.task_id,
            "task_status": task.status,
            "retry_count": task.retry_count,
            "max_retry": task.max_retry,
            "result_status": result_status,
            "retryable": retryable,
        }
        if sender_id is not None:
            detail["sender_id"] = sender_id
        if error_code is not None:
            detail["error_code"] = error_code
        if error_message is not None:
            detail["error_message"] = error_message
        if callback_detail:
            detail["callback_detail"] = callback_detail
        if extra:
            detail.update(extra)
        return detail


def build_pending_task_payload(task: DispatchTask) -> dict[str, object]:
    return {
        "task_id": task.task_id,
        "report_date": task.report.report_date.isoformat(),
        "task_type": task.task_type,
        "target_user": task.target_user,
        "message_chunks": list(build_message_chunks_from_payload(task.payload)),
        "max_retry": task.max_retry,
        "created_at": task.created_at.isoformat(),
    }
