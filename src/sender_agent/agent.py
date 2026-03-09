from __future__ import annotations

import logging
import socket
from datetime import datetime
from threading import Event, Lock, Thread, current_thread

from sender_agent.api_client import SenderApiClient
from sender_agent.config import SenderSettings
from sender_agent.errors import SenderApiError, SenderNetworkError, WechatLoggedOutError, WechatWindowNotFoundError
from sender_agent.executor import TaskExecutor
from sender_agent.models import SenderEventPayload, SenderHeartbeatPayload, SenderTaskResultPayload
from sender_agent.task_journal import TaskJournal
from sender_agent.wechat.base import WechatAutomation

logger = logging.getLogger(__name__)


class SenderAgent:
    def __init__(
        self,
        *,
        settings: SenderSettings,
        api_client: SenderApiClient,
        task_journal: TaskJournal,
        executor: TaskExecutor,
        wechat: WechatAutomation,
    ) -> None:
        self.settings = settings
        self.api_client = api_client
        self.task_journal = task_journal
        self.executor = executor
        self.wechat = wechat
        self._stop_event = Event()
        self._heartbeat_lock = Lock()
        self._heartbeat_interval = settings.heartbeat_interval_seconds
        self._last_login_status = "unknown"
        self._last_event_signature: tuple[str, str] | None = None
        self._heartbeat_thread: Thread | None = None

    def run(self) -> None:
        self._heartbeat_thread = Thread(target=self._heartbeat_loop, name="sender-heartbeat", daemon=True)
        self._heartbeat_thread.start()
        try:
            while not self._stop_event.is_set():
                self._flush_pending_results()
                login_status = self._safe_wechat_status()
                if login_status != "logged_in":
                    self._handle_unavailable_status(login_status)
                    self._stop_event.wait(self.settings.poll_interval_seconds)
                    continue

                self._last_event_signature = None
                tasks = self.api_client.fetch_pending_tasks(
                    sender_id=self.settings.sender_id,
                    limit=self.settings.task_limit,
                )
                if not tasks:
                    self._stop_event.wait(self.settings.poll_interval_seconds)
                    continue

                for task in tasks:
                    result = self.executor.execute(task)
                    try:
                        self._submit_task_result(task.task_id, result)
                    except SenderNetworkError as exc:
                        logger.warning("Result callback network failure for task_id=%s: %s", task.task_id, exc)
                        return
                    except SenderApiError as exc:
                        logger.warning("Result callback API failure for task_id=%s: %s", task.task_id, exc)
                        if exc.status_code == 409 and "conflict" in str(exc).lower():
                            self.task_journal.mark_result_confirmed(task.task_id)
                            continue
                        raise
                    if self._stop_event.is_set():
                        break
        finally:
            self.stop()

    def stop(self) -> None:
        self._stop_event.set()
        if self._heartbeat_thread and self._heartbeat_thread.is_alive() and self._heartbeat_thread is not current_thread():
            self._heartbeat_thread.join(timeout=2)
        self.api_client.close()

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self._send_heartbeat()
            except SenderNetworkError as exc:
                logger.warning("Heartbeat failed due to network error: %s", exc)
                self._report_event_once(
                    event_type="network_unavailable",
                    message=str(exc),
                    level="warning",
                )
            except Exception as exc:  # pragma: no cover - safety net
                logger.exception("Unexpected heartbeat error: %s", exc)
                self._report_event_once(
                    event_type="sender_process_error",
                    message=str(exc),
                    level="error",
                )
            self._stop_event.wait(self._heartbeat_interval)

    def _send_heartbeat(self) -> None:
        with self._heartbeat_lock:
            login_status = self._safe_wechat_status()
            payload = SenderHeartbeatPayload(
                sender_id=self.settings.sender_id,
                status="online" if login_status == "logged_in" else "degraded",
                wechat_login_status=login_status,
                client_version=self.settings.client_version,
                host_name=socket.gethostname(),
                ip=self.settings.heartbeat_ip,
                timestamp=datetime.now().astimezone(),
            )
            response = self.api_client.send_heartbeat(payload)
            self._heartbeat_interval = max(5, response.next_heartbeat_in_seconds)
            self._last_login_status = login_status

    def _safe_wechat_status(self) -> str:
        try:
            return self.wechat.check_login_status()
        except WechatLoggedOutError:
            return "logged_out"
        except WechatWindowNotFoundError:
            return "unknown"
        except Exception as exc:
            logger.warning("Unable to determine WeChat status: %s", exc)
            return "unknown"

    def _handle_unavailable_status(self, login_status: str) -> None:
        if login_status == "logged_out":
            self._report_event_once(
                event_type="wechat_logged_out",
                message="WeChat session is unavailable; waiting for manual login recovery",
                level="warning",
            )
        else:
            self._report_event_once(
                event_type="wechat_window_not_found",
                message="WeChat desktop window was not found; waiting for manual recovery",
                level="warning",
            )

    def _submit_task_result(self, task_id: str, result) -> None:
        response = self.api_client.report_task_result(task_id, result)
        logger.info("Reported result for task_id=%s task_status=%s", task_id, response.task_status)
        self.task_journal.mark_result_confirmed(task_id)

    def _flush_pending_results(self) -> None:
        pending_reports = self.task_journal.list_pending_results()
        for pending in pending_reports:
            try:
                result = SenderTaskResultPayload.model_validate(pending.payload)
                self._submit_task_result(pending.task_id, result)
            except SenderApiError as exc:
                logger.warning("Pending result replay failed for task_id=%s: %s", pending.task_id, exc)
                if exc.status_code == 409 and "conflict" in str(exc).lower():
                    self.task_journal.mark_result_confirmed(pending.task_id)
                return
            except SenderNetworkError as exc:
                logger.warning("Pending result replay network failure for task_id=%s: %s", pending.task_id, exc)
                return

    def _report_event_once(self, *, event_type: str, message: str, level: str) -> None:
        signature = (event_type, message)
        if self._last_event_signature == signature:
            return
        try:
            payload = SenderEventPayload(
                sender_id=self.settings.sender_id,
                event_type=event_type,  # type: ignore[arg-type]
                level=level,  # type: ignore[arg-type]
                message=message,
                occurred_at=datetime.now().astimezone(),
                detail={},
            )
            self.api_client.report_event(payload)
            self._last_event_signature = signature
        except (SenderApiError, SenderNetworkError) as exc:
            logger.warning("Failed to report sender event event_type=%s: %s", event_type, exc)
