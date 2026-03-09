from __future__ import annotations

from datetime import datetime
from pathlib import Path
from threading import current_thread

import pytest

from sender_agent.agent import SenderAgent
from sender_agent.config import SenderSettings
from sender_agent.errors import SenderApiError, SenderNetworkError
from sender_agent.models import SenderHeartbeatResponseData, SenderTaskResultPayload
from sender_agent.task_journal import TaskJournal
from sender_agent.wechat.base import WechatAutomation


class StopLoop(Exception):
    pass


class DummyWechat(WechatAutomation):
    def __init__(self, status: str = "logged_in") -> None:
        self.status = status

    def check_login_status(self):
        return self.status

    def ensure_ready(self) -> None:
        return None

    def open_chat(self, target_user: str) -> None:
        return None

    def send_text(self, text: str) -> None:
        return None


class DummyTask:
    def __init__(self, task_id: str = "task-1") -> None:
        self.task_id = task_id
        self.target_user = "测试联系人"
        self.task_type = "daily_report"


class DummyApiClient:
    def __init__(self) -> None:
        self.closed = False
        self.heartbeats = []
        self.events = []
        self.fetch_calls = []
        self.reported_results = []
        self.tasks_to_return = []
        self.report_result_exception = None

    def send_heartbeat(self, payload):
        self.heartbeats.append(payload)
        return SenderHeartbeatResponseData(
            server_time=datetime.fromisoformat("2026-03-08T08:00:00+08:00"),
            next_heartbeat_in_seconds=42,
        )

    def fetch_pending_tasks(self, *, sender_id: str, limit: int):
        self.fetch_calls.append((sender_id, limit))
        tasks = list(self.tasks_to_return)
        self.tasks_to_return = []
        return tasks

    def report_task_result(self, task_id: str, result):
        self.reported_results.append((task_id, result))
        if self.report_result_exception is not None:
            raise self.report_result_exception
        return type("ResultResponse", (), {"task_status": "sent"})()

    def report_event(self, payload):
        self.events.append(payload)
        return {"ok": True}

    def close(self) -> None:
        self.closed = True


class DummyExecutor:
    def __init__(self, journal: TaskJournal | None = None) -> None:
        self.journal = journal
        self.tasks = []
        self.result = SenderTaskResultPayload(
            sender_id="sender-01",
            success=True,
            status="sent",
            retryable=False,
            sent_at=datetime.fromisoformat("2026-03-08T08:01:00+08:00"),
            detail={"chunk_count": 1},
        )

    def execute(self, task):
        self.tasks.append(task)
        if self.journal is not None:
            self.journal.upsert(
                task_id=task.task_id,
                target_user=task.target_user,
                task_type=task.task_type,
                status="result_pending",
                sent_chunks=self.result.detail.get("chunk_count", 0),
                result_payload=self.result.model_dump(mode="json"),
            )
        return self.result


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


def build_agent(tmp_path: Path, *, wechat: DummyWechat | None = None, api_client: DummyApiClient | None = None, executor: DummyExecutor | None = None) -> tuple[SenderAgent, DummyApiClient, DummyExecutor, TaskJournal]:
    settings = build_settings(tmp_path)
    api = api_client or DummyApiClient()
    journal = TaskJournal(settings.journal_path)
    exec_ = executor or DummyExecutor(journal)
    agent = SenderAgent(
        settings=settings,
        api_client=api,
        task_journal=journal,
        executor=exec_,
        wechat=wechat or DummyWechat(status="logged_in"),
    )
    return agent, api, exec_, journal


def test_send_heartbeat_updates_interval_and_status(tmp_path: Path) -> None:
    agent, api_client, _, _ = build_agent(tmp_path)

    agent._send_heartbeat()

    assert len(api_client.heartbeats) == 1
    assert api_client.heartbeats[0].status == "online"
    assert api_client.heartbeats[0].wechat_login_status == "logged_in"
    assert agent._heartbeat_interval == 42


def test_stop_skips_join_for_current_thread(tmp_path: Path) -> None:
    agent, api_client, _, _ = build_agent(tmp_path)
    agent._heartbeat_thread = current_thread()

    agent.stop()

    assert api_client.closed is True


def test_flush_pending_results_marks_confirmed_after_successful_replay(tmp_path: Path) -> None:
    agent, api_client, _, journal = build_agent(tmp_path)
    payload = SenderTaskResultPayload(
        sender_id="sender-01",
        success=True,
        status="sent",
        retryable=False,
        sent_at=datetime.fromisoformat("2026-03-08T08:10:00+08:00"),
        detail={"chunk_count": 1},
    )
    journal.upsert(
        task_id="task-replay",
        target_user="测试联系人",
        task_type="daily_report",
        status="result_pending",
        sent_chunks=1,
        result_payload=payload.model_dump(mode="json"),
    )

    agent._flush_pending_results()

    record = journal.get("task-replay")
    assert record is not None
    assert record.status == "result_confirmed"
    assert api_client.reported_results[0][0] == "task-replay"


def test_run_stops_after_result_callback_network_failure(tmp_path: Path) -> None:
    agent, api_client, executor, journal = build_agent(tmp_path)
    task = DummyTask("task-network")
    api_client.tasks_to_return = [task]
    api_client.report_result_exception = SenderNetworkError("network down")

    agent.run()

    assert executor.tasks == [task]
    record = journal.get("task-network")
    assert record is not None
    assert record.status == "result_pending"


def test_run_marks_conflicted_result_as_confirmed(tmp_path: Path) -> None:
    agent, api_client, executor, journal = build_agent(tmp_path)
    task = DummyTask("task-conflict")
    api_client.report_result_exception = SenderApiError("task status conflict", status_code=409)

    fetch_count = 0

    def fetch_pending_tasks(*, sender_id: str, limit: int):
        nonlocal fetch_count
        api_client.fetch_calls.append((sender_id, limit))
        fetch_count += 1
        if fetch_count == 1:
            return [task]
        agent._stop_event.set()
        return []

    api_client.fetch_pending_tasks = fetch_pending_tasks

    agent.run()

    assert executor.tasks == [task]
    record = journal.get("task-conflict")
    assert record is not None
    assert record.status == "result_confirmed"


def test_run_reports_logged_out_event_and_skips_fetch(tmp_path: Path) -> None:
    agent, api_client, _, _ = build_agent(tmp_path, wechat=DummyWechat(status="logged_out"))

    def stop_after_report(*, event_type: str, message: str, level: str) -> None:
        SenderAgent._report_event_once(agent, event_type=event_type, message=message, level=level)
        raise StopLoop

    agent._report_event_once = stop_after_report
    try:
        with pytest.raises(StopLoop):
            agent.run()
    finally:
        agent.stop()

    assert api_client.fetch_calls == []
    assert len(api_client.events) == 1
    assert api_client.events[0].event_type == "wechat_logged_out"


def test_run_deduplicates_repeated_logged_out_event(tmp_path: Path) -> None:
    agent, api_client, _, _ = build_agent(tmp_path, wechat=DummyWechat(status="logged_out"))

    agent._handle_unavailable_status("logged_out")
    agent._handle_unavailable_status("logged_out")

    assert len(api_client.events) == 1
    assert api_client.events[0].event_type == "wechat_logged_out"
