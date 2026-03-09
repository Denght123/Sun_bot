from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from sender_agent.config import SenderSettings
from sender_agent.errors import WechatLoggedOutError, WechatPartialSendError, WechatWindowNotFoundError
from sender_agent.executor import TaskExecutor
from sender_agent.models import PendingDispatchTask
from sender_agent.task_journal import TaskJournal
from sender_agent.wechat.base import WechatAutomation


class DummyWechat(WechatAutomation):
    def __init__(self, failure: Exception | None = None) -> None:
        self.sent: list[tuple[str, list[str]]] = []
        self.failure = failure

    def check_login_status(self):
        return "logged_in"

    def ensure_ready(self) -> None:
        return None

    def open_chat(self, target_user: str) -> None:
        self._target_user = target_user

    def send_text(self, text: str) -> None:
        return None

    def send_chunks(self, target_user: str, chunks: list[str]) -> int:
        if self.failure is not None:
            raise self.failure
        self.sent.append((target_user, chunks))
        return len(chunks)


class DummyApiClient:
    pass


def build_settings(tmp_path: Path) -> SenderSettings:
    return SenderSettings(
        api_base_url="http://127.0.0.1:8000/api",
        sender_token="token-123",
        sender_id="sender-01",
        timezone="Asia/Shanghai",
        log_level="INFO",
        heartbeat_interval_seconds=30,
        poll_interval_seconds=5,
        request_timeout_seconds=10,
        task_limit=1,
        client_version="0.1.0",
        local_state_dir=tmp_path,
        log_file=tmp_path / "sender.log",
        journal_path=tmp_path / "sender.sqlite3",
        wechat_window_title_hint="微信",
        wechat_send_delay_ms=300,
        wechat_chat_search_timeout_seconds=10,
        heartbeat_ip=None,
    )


def build_task(task_id: str = "task-1") -> PendingDispatchTask:
    return PendingDispatchTask(
        task_id=task_id,
        report_date=datetime.fromisoformat("2026-03-08T00:00:00+08:00").date(),
        task_type="daily_report",
        target_user="测试联系人",
        message_chunks=["第一段", "第二段"],
        max_retry=3,
        created_at=datetime.fromisoformat("2026-03-08T07:59:00+08:00"),
    )


def build_executor(tmp_path: Path, *, wechat: DummyWechat | None = None) -> tuple[TaskExecutor, TaskJournal, DummyWechat]:
    settings = build_settings(tmp_path)
    journal = TaskJournal(settings.journal_path)
    bound_wechat = wechat or DummyWechat()
    executor = TaskExecutor(
        settings=settings,
        api_client=DummyApiClient(),
        task_journal=journal,
        wechat=bound_wechat,
    )
    return executor, journal, bound_wechat


def test_task_executor_executes_daily_report_and_records_pending_result(tmp_path: Path) -> None:
    executor, journal, wechat = build_executor(tmp_path)
    task = build_task()

    result = executor.execute(task)

    assert result.success is True
    assert result.status == "sent"
    assert result.retryable is False
    assert wechat.sent == [("测试联系人", ["第一段", "第二段"])]

    record = journal.get("task-1")
    assert record is not None
    assert record.status == "result_pending"
    assert record.sent_chunks == 2
    assert record.result_payload is not None
    assert record.result_payload["status"] == "sent"


@pytest.mark.parametrize(
    ("failure", "expected_status", "expected_retryable", "expected_sent_chunks", "expected_error_type"),
    [
        (WechatLoggedOutError("logged out"), "failed", True, 0, "wechat_logged_out"),
        (WechatWindowNotFoundError("window missing"), "failed", True, 0, "wechat_window_not_found"),
        (WechatPartialSendError("partial send", sent_chunks=1), "partial", False, 1, "wechat_partial_send"),
    ],
)
def test_task_executor_classifies_wechat_failures(
    tmp_path: Path,
    failure: Exception,
    expected_status: str,
    expected_retryable: bool,
    expected_sent_chunks: int,
    expected_error_type: str,
) -> None:
    executor, journal, _ = build_executor(tmp_path, wechat=DummyWechat(failure=failure))

    result = executor.execute(build_task(task_id=f"task-{expected_error_type}"))

    assert result.success is False
    assert result.status == expected_status
    assert result.retryable is expected_retryable
    assert result.detail["error_type"] == expected_error_type

    record = journal.get(f"task-{expected_error_type}")
    assert record is not None
    assert record.status == "result_pending"
    assert record.sent_chunks == expected_sent_chunks


def test_task_executor_returns_recorded_result_for_duplicate_task(tmp_path: Path) -> None:
    executor, journal, wechat = build_executor(tmp_path)
    first_result = executor.execute(build_task(task_id="task-dup"))

    second_result = executor.execute(build_task(task_id="task-dup"))

    assert second_result.model_dump(mode="json") == first_result.model_dump(mode="json")
    assert wechat.sent == [("测试联系人", ["第一段", "第二段"])]
