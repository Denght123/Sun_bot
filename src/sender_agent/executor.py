from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sender_agent.api_client import SenderApiClient
from sender_agent.config import SenderSettings
from sender_agent.errors import WechatLoggedOutError, WechatPartialSendError, WechatWindowNotFoundError
from sender_agent.models import PendingDispatchTask, SenderTaskResultPayload, TaskResultStatus
from sender_agent.task_journal import TaskJournal
from sender_agent.wechat.base import WechatAutomation

logger = logging.getLogger(__name__)


class TaskExecutor:
    def __init__(
        self,
        *,
        settings: SenderSettings,
        api_client: SenderApiClient,
        task_journal: TaskJournal,
        wechat: WechatAutomation,
    ) -> None:
        self.settings = settings
        self.api_client = api_client
        self.task_journal = task_journal
        self.wechat = wechat

    def execute(self, task: PendingDispatchTask) -> SenderTaskResultPayload:
        existing = self.task_journal.get(task.task_id)
        if existing is not None and existing.status in {"result_pending", "result_confirmed"} and existing.result_payload:
            logger.info("Skipping duplicate task execution for task_id=%s", task.task_id)
            return SenderTaskResultPayload.model_validate(existing.result_payload)

        self.task_journal.upsert(
            task_id=task.task_id,
            target_user=task.target_user,
            task_type=task.task_type,
            status="claimed",
        )

        if task.task_type != "daily_report":
            result = self._build_result(
                task=task,
                success=False,
                status="failed",
                retryable=False,
                error_message=f"Unsupported task type: {task.task_type}",
                detail={"unsupported_task_type": task.task_type},
            )
            self._record_pending_result(task, result, sent_chunks=0, last_error=result.error_message)
            return result

        try:
            self.task_journal.upsert(
                task_id=task.task_id,
                target_user=task.target_user,
                task_type=task.task_type,
                status="sending",
            )
            sent_count = self.wechat.send_chunks(task.target_user, task.message_chunks)
        except WechatLoggedOutError as exc:
            result = self._build_result(
                task=task,
                success=False,
                status="failed",
                retryable=True,
                error_message=str(exc),
                detail={"error_type": "wechat_logged_out", "sent_chunks": 0},
            )
            self._record_pending_result(task, result, sent_chunks=0, last_error=str(exc))
            return result
        except WechatWindowNotFoundError as exc:
            result = self._build_result(
                task=task,
                success=False,
                status="failed",
                retryable=True,
                error_message=str(exc),
                detail={"error_type": "wechat_window_not_found", "sent_chunks": 0},
            )
            self._record_pending_result(task, result, sent_chunks=0, last_error=str(exc))
            return result
        except WechatPartialSendError as exc:
            result = self._build_result(
                task=task,
                success=False,
                status="partial",
                retryable=False,
                error_message=str(exc),
                detail={"error_type": "wechat_partial_send", "sent_chunks": exc.sent_chunks},
            )
            self._record_pending_result(task, result, sent_chunks=exc.sent_chunks, last_error=str(exc))
            return result
        except Exception as exc:
            result = self._build_result(
                task=task,
                success=False,
                status="failed",
                retryable=True,
                error_message=str(exc),
                detail={"error_type": type(exc).__name__, "sent_chunks": 0},
            )
            self._record_pending_result(task, result, sent_chunks=0, last_error=str(exc))
            return result

        result = self._build_result(
            task=task,
            success=True,
            status="sent",
            retryable=False,
            error_message=None,
            detail={"chunk_count": sent_count, "target_user": task.target_user},
        )
        self._record_pending_result(task, result, sent_chunks=sent_count, last_error=None)
        return result

    def _record_pending_result(
        self,
        task: PendingDispatchTask,
        result: SenderTaskResultPayload,
        *,
        sent_chunks: int,
        last_error: str | None,
    ) -> None:
        self.task_journal.upsert(
            task_id=task.task_id,
            target_user=task.target_user,
            task_type=task.task_type,
            status="result_pending",
            sent_chunks=sent_chunks,
            last_error=last_error,
            result_payload=result.model_dump(mode="json"),
        )

    def _build_result(
        self,
        *,
        task: PendingDispatchTask,
        success: bool,
        status: TaskResultStatus,
        retryable: bool,
        error_message: str | None,
        detail: dict[str, Any],
    ) -> SenderTaskResultPayload:
        return SenderTaskResultPayload(
            sender_id=self.settings.sender_id,
            success=success,
            status=status,
            error_message=error_message,
            retryable=retryable,
            sent_at=datetime.now().astimezone(),
            detail={"task_id": task.task_id, **detail},
        )
