from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.scheduler.bootstrap as scheduler_bootstrap
import app.services.scheduler_dispatch_flow as scheduler_flow_module
from app.collectors.base import CollectedItem
from app.core.config import get_settings
from app.core.time import now_in_timezone
from app.db.base import Base
from app.db.model_definitions import DailyReport, DispatchAttempt, DispatchTask, EventCluster, EventSource, RawItem, SystemEvent
from app.db.session import get_db
from app.main import create_app
from app.services.collection_pipeline import CollectionPipeline

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
API_PREFIX = get_settings().api_prefix


class FixtureCollector:
    def __init__(self, source_platform: str, items: list[CollectedItem]) -> None:
        self.source_platform = source_platform
        self._items = items

    def collect(self) -> list[CollectedItem]:
        return self._items


class DummySession:
    def __init__(self) -> None:
        self.closed = False
        self.rollback_called = False
        self.commit_called = False

    def commit(self) -> None:
        self.commit_called = True

    def rollback(self) -> None:
        self.rollback_called = True

    def close(self) -> None:
        self.closed = True


def load_fixture_items() -> list[CollectedItem]:
    batch = json.loads((FIXTURES / "pipeline" / "mixed_batch.json").read_text(encoding="utf-8"))
    return [CollectedItem(**row) for row in batch]


def build_fixture_collectors() -> list[FixtureCollector]:
    grouped: dict[str, list[CollectedItem]] = {}
    for item in load_fixture_items():
        grouped.setdefault(item.source_platform, []).append(item)
    return [FixtureCollector(source_platform=source, items=items) for source, items in grouped.items()]


def build_sqlite_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


def test_collection_pipeline_end_to_end() -> None:
    engine = build_sqlite_engine()
    settings = get_settings().model_copy(update={"candidate_event_limit_per_section": 10})

    with Session(engine) as session:
        pipeline = CollectionPipeline(session=session, settings=settings, collectors=build_fixture_collectors())
        result = pipeline.run(report_date=date(2026, 3, 7))

        raw_items = session.query(RawItem).all()
        event_clusters = session.query(EventCluster).all()
        event_sources = session.query(EventSource).all()

        assert result.sources == ["cls", "baidu"]
        assert result.collected_count == 4
        assert result.inserted_count == 4
        assert len(raw_items) == 4
        assert any(item.process_status == "filtered" for item in raw_items)
        assert len(event_clusters) >= 2
        assert len(event_sources) >= 2
        assert result.candidate_feed.sections["policy"]
        assert result.candidate_feed.sections["sector"]


def test_admin_report_run_route_creates_report_and_dispatch_task(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = build_sqlite_engine()
    settings = get_settings().model_copy(update={"candidate_event_limit_per_section": 10})
    app = create_app()

    def override_get_db():
        with Session(engine) as session:
            yield session

    def fake_run_collection_pipeline(*, session: Session, report_date: date | None = None):
        pipeline = CollectionPipeline(session=session, settings=settings, collectors=build_fixture_collectors())
        return pipeline.run(report_date=report_date)

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(scheduler_flow_module, "run_collection_pipeline", fake_run_collection_pipeline)

    try:
        with TestClient(app) as client:
            response = client.post(
                f"{API_PREFIX}/admin/report/run",
                headers={"Authorization": f"Bearer {settings.admin_token}"},
                json={"report_date": "2026-03-07"},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"]["status"] == "completed"
    assert body["data"]["report_date"] == "2026-03-07"
    assert body["data"]["generation_status"] == "success"
    assert len(body["data"]["dispatch_task_ids"]) == 1

    with Session(engine) as session:
        report = session.query(DailyReport).one()
        task = session.query(DispatchTask).one()

        assert report.report_date == date(2026, 3, 7)
        assert report.generation_status == "success"
        assert task.report_id == report.id
        assert task.status == "waiting_sender"
        assert task.payload["message_chunks"]


def test_sender_routes_dispatch_and_complete_task() -> None:
    engine = build_sqlite_engine()
    settings = get_settings()
    app = create_app()
    report_date = date(2026, 3, 7)
    now = now_in_timezone()

    with Session(engine) as session:
        report = DailyReport(
            report_date=report_date,
            generation_status="success",
            fallback_used=False,
            data_window_start=now,
            data_window_end=now,
            total_word_count=12,
            total_message_chunks=1,
            full_text="日报正文",
            link_bundle={"message_chunks": ["日报正文"]},
            generated_at=now,
        )
        session.add(report)
        session.flush()
        session.add(
            DispatchTask(
                task_id="task_20260307_test",
                report_id=report.id,
                sender_id=None,
                target_user="my_wechat_id",
                task_type="daily_report",
                payload={"message_chunks": ["日报正文"], "full_text": "日报正文"},
                status="waiting_sender",
                retry_count=0,
                max_retry=3,
                scheduled_at=now,
            )
        )
        session.commit()

    def override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            heartbeat_response = client.post(
                f"{API_PREFIX}/sender/heartbeat",
                headers={"Authorization": f"Bearer {settings.sender_token}"},
                json={
                    "sender_id": "sender-01",
                    "status": "online",
                    "wechat_login_status": "logged_in",
                    "timestamp": now.isoformat(),
                },
            )
            assert heartbeat_response.status_code == 200
            assert heartbeat_response.json()["data"]["next_heartbeat_in_seconds"] == settings.sender_next_heartbeat_seconds

            pending_response = client.get(
                f"{API_PREFIX}/sender/tasks/pending",
                headers={"Authorization": f"Bearer {settings.sender_token}"},
                params={"sender_id": "sender-01", "limit": 1},
            )
            assert pending_response.status_code == 200
            pending_tasks = pending_response.json()["data"]["tasks"]
            assert len(pending_tasks) == 1
            assert pending_tasks[0]["task_id"] == "task_20260307_test"
            assert pending_tasks[0]["message_chunks"] == ["日报正文"]

            result_response = client.post(
                f"{API_PREFIX}/sender/tasks/task_20260307_test/result",
                headers={"Authorization": f"Bearer {settings.sender_token}"},
                json={
                    "sender_id": "sender-01",
                    "success": True,
                    "status": "sent",
                    "retryable": False,
                    "sent_at": now.isoformat(),
                    "detail": {"platform": "wechat"},
                },
            )
            assert result_response.status_code == 200
            assert result_response.json()["data"]["task_status"] == "sent"

            duplicate_result_response = client.post(
                f"{API_PREFIX}/sender/tasks/task_20260307_test/result",
                headers={"Authorization": f"Bearer {settings.sender_token}"},
                json={
                    "sender_id": "sender-01",
                    "success": True,
                    "status": "sent",
                    "retryable": False,
                    "sent_at": now.isoformat(),
                    "detail": {"platform": "wechat", "duplicate": True},
                },
            )
            assert duplicate_result_response.status_code == 200
            assert duplicate_result_response.json()["data"]["task_status"] == "sent"

            event_response = client.post(
                f"{API_PREFIX}/sender/events",
                headers={"Authorization": f"Bearer {settings.sender_token}"},
                json={
                    "sender_id": "sender-01",
                    "event_type": "wechat_logged_out",
                    "level": "warning",
                    "message": "wechat session lost",
                    "occurred_at": now.isoformat(),
                    "detail": {"source": "sender-agent"},
                },
            )
            assert event_response.status_code == 200
            assert event_response.json()["data"]["event_type"] == "wechat_logged_out"
    finally:
        app.dependency_overrides.clear()

    with Session(engine) as session:
        task = session.query(DispatchTask).one()
        attempts = session.query(DispatchAttempt).all()
        system_events = session.query(SystemEvent).all()

        assert task.sender_id == "sender-01"
        assert task.status == "sent"
        assert task.sent_at is not None
        assert len(attempts) == 1
        assert attempts[0].status == "success"
        assert len(system_events) == 1
        assert system_events[0].event_type == "wechat_logged_out"
        assert system_events[0].object_type == "sender"
        assert system_events[0].object_id == "sender-01"




def test_sender_routes_retry_and_record_failure_state() -> None:
    engine = build_sqlite_engine()
    settings = get_settings()
    app = create_app()
    report_date = date(2026, 3, 7)
    now = now_in_timezone()

    with Session(engine) as session:
        report = DailyReport(
            report_date=report_date,
            generation_status="success",
            fallback_used=False,
            data_window_start=now,
            data_window_end=now,
            total_word_count=12,
            total_message_chunks=1,
            full_text="日报正文",
            link_bundle={"message_chunks": ["日报正文"]},
            generated_at=now,
        )
        session.add(report)
        session.flush()
        session.add(
            DispatchTask(
                task_id="task_20260307_retry",
                report_id=report.id,
                sender_id=None,
                target_user="my_wechat_id",
                task_type="daily_report",
                payload={"message_chunks": ["日报正文"], "full_text": "日报正文", "channel": "wechat"},
                status="waiting_sender",
                retry_count=0,
                max_retry=3,
                scheduled_at=now,
            )
        )
        session.commit()

    def override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            heartbeat_response = client.post(
                f"{API_PREFIX}/sender/heartbeat",
                headers={"Authorization": f"Bearer {settings.sender_token}"},
                json={
                    "sender_id": "sender-01",
                    "status": "online",
                    "wechat_login_status": "logged_in",
                    "timestamp": now.isoformat(),
                },
            )
            assert heartbeat_response.status_code == 200

            pending_response = client.get(
                f"{API_PREFIX}/sender/tasks/pending",
                headers={"Authorization": f"Bearer {settings.sender_token}"},
                params={"sender_id": "sender-01", "limit": 1},
            )
            assert pending_response.status_code == 200
            pending_tasks = pending_response.json()["data"]["tasks"]
            assert len(pending_tasks) == 1
            assert pending_tasks[0]["task_id"] == "task_20260307_retry"
            assert pending_tasks[0]["target_user"] == "my_wechat_id"

            first_failure = client.post(
                f"{API_PREFIX}/sender/tasks/task_20260307_retry/result",
                headers={"Authorization": f"Bearer {settings.sender_token}"},
                json={
                    "sender_id": "sender-01",
                    "success": False,
                    "status": "failed",
                    "retryable": True,
                    "error_message": "wechat_send_failed",
                    "sent_at": now.isoformat(),
                    "detail": {"platform": "wechat", "error_code": 40014},
                },
            )
            assert first_failure.status_code == 200
            assert first_failure.json()["data"]["task_status"] == "pending"

            second_pending = client.get(
                f"{API_PREFIX}/sender/tasks/pending",
                headers={"Authorization": f"Bearer {settings.sender_token}"},
                params={"sender_id": "sender-01", "limit": 1},
            )
            assert second_pending.status_code == 200
            second_pending_tasks = second_pending.json()["data"]["tasks"]
            assert len(second_pending_tasks) == 1
            assert second_pending_tasks[0]["task_id"] == "task_20260307_retry"

            second_failure = client.post(
                f"{API_PREFIX}/sender/tasks/task_20260307_retry/result",
                headers={"Authorization": f"Bearer {settings.sender_token}"},
                json={
                    "sender_id": "sender-01",
                    "success": False,
                    "status": "failed",
                    "retryable": False,
                    "error_message": "wechat_session_expired",
                    "sent_at": now.isoformat(),
                    "detail": {"platform": "wechat", "error_code": 42001},
                },
            )
            assert second_failure.status_code == 200
            assert second_failure.json()["data"]["task_status"] == "failed"

            task_detail = client.get(
                f"{API_PREFIX}/admin/tasks/task_20260307_retry",
                headers={"Authorization": f"Bearer {settings.admin_token}"},
            )
            assert task_detail.status_code == 200
            detail_data = task_detail.json()["data"]
            assert detail_data["status"] == "failed"
            assert detail_data["retry_count"] == 2
            assert detail_data["last_error"] == "wechat_session_expired"
    finally:
        app.dependency_overrides.clear()

    with Session(engine) as session:
        task = session.query(DispatchTask).filter(DispatchTask.task_id == "task_20260307_retry").one()
        attempts = session.query(DispatchAttempt).filter(DispatchAttempt.dispatch_task_id == task.id).order_by(DispatchAttempt.attempt_no).all()
        system_events = session.query(SystemEvent).filter(SystemEvent.object_id == task.task_id).order_by(SystemEvent.id).all()

        assert task.status == "failed"
        assert task.retry_count == 2
        assert task.last_error == "wechat_session_expired"
        assert task.sender_id is None
        assert len(attempts) == 2
        assert [attempt.status for attempt in attempts] == ["failed", "failed"]
        assert attempts[0].retryable is True
        assert attempts[0].error_code == "40014"
        assert attempts[1].retryable is False
        assert attempts[1].error_code == "42001"
        assert attempts[1].error_message == "wechat_session_expired"
        assert len(system_events) == 1
        assert system_events[0].event_type == "dispatch_task_failed"
        assert system_events[0].detail["error_code"] == "42001"


def test_sender_routes_partial_result_is_normalized_to_failed_attempt_and_event() -> None:
    engine = build_sqlite_engine()
    settings = get_settings()
    app = create_app()
    report_date = date(2026, 3, 7)
    now = now_in_timezone()

    with Session(engine) as session:
        report = DailyReport(
            report_date=report_date,
            generation_status="success",
            fallback_used=False,
            data_window_start=now,
            data_window_end=now,
            total_word_count=12,
            total_message_chunks=2,
            full_text="日报正文",
            link_bundle={"message_chunks": ["第一段", "第二段"]},
            generated_at=now,
        )
        session.add(report)
        session.flush()
        session.add(
            DispatchTask(
                task_id="task_20260307_partial",
                report_id=report.id,
                sender_id=None,
                target_user="my_wechat_id",
                task_type="daily_report",
                payload={"message_chunks": ["第一段", "第二段"], "full_text": "日报正文", "channel": "wechat"},
                status="waiting_sender",
                retry_count=0,
                max_retry=3,
                scheduled_at=now,
            )
        )
        session.commit()

    def override_get_db():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            heartbeat_response = client.post(
                f"{API_PREFIX}/sender/heartbeat",
                headers={"Authorization": f"Bearer {settings.sender_token}"},
                json={
                    "sender_id": "sender-01",
                    "status": "online",
                    "wechat_login_status": "logged_in",
                    "timestamp": now.isoformat(),
                },
            )
            assert heartbeat_response.status_code == 200

            pending_response = client.get(
                f"{API_PREFIX}/sender/tasks/pending",
                headers={"Authorization": f"Bearer {settings.sender_token}"},
                params={"sender_id": "sender-01", "limit": 1},
            )
            assert pending_response.status_code == 200
            assert pending_response.json()["data"]["tasks"][0]["task_id"] == "task_20260307_partial"

            partial_result = client.post(
                f"{API_PREFIX}/sender/tasks/task_20260307_partial/result",
                headers={"Authorization": f"Bearer {settings.sender_token}"},
                json={
                    "sender_id": "sender-01",
                    "success": False,
                    "status": "partial",
                    "retryable": False,
                    "error_message": "partial send",
                    "sent_at": now.isoformat(),
                    "detail": {"platform": "wechat", "error_code": "wechat_partial_send", "sent_chunks": 1},
                },
            )
            assert partial_result.status_code == 200
            assert partial_result.json()["data"]["task_status"] == "failed"
    finally:
        app.dependency_overrides.clear()

    with Session(engine) as session:
        task = session.query(DispatchTask).filter(DispatchTask.task_id == "task_20260307_partial").one()
        attempts = session.query(DispatchAttempt).filter(DispatchAttempt.dispatch_task_id == task.id).all()
        system_events = session.query(SystemEvent).filter(SystemEvent.object_id == task.task_id).all()

        assert task.status == "failed"
        assert task.retry_count == 1
        assert task.last_error == "partial send"
        assert len(attempts) == 1
        assert attempts[0].status == "failed"
        assert attempts[0].retryable is False
        assert attempts[0].error_code == "wechat_partial_send"
        assert len(system_events) == 1
        assert system_events[0].event_type == "dispatch_partial_send"
        assert system_events[0].detail["result_status"] == "partial"
        assert system_events[0].detail["callback_detail"]["sent_chunks"] == 1


def test_fetch_pending_tasks_recovers_stale_dispatch_before_redelivery() -> None:
    engine = build_sqlite_engine()
    now = now_in_timezone()

    with Session(engine) as session:
        report = DailyReport(
            report_date=date(2026, 3, 7),
            generation_status="success",
            fallback_used=False,
            data_window_start=now,
            data_window_end=now,
            total_word_count=12,
            total_message_chunks=1,
            full_text="日报正文",
            link_bundle={"message_chunks": ["日报正文"]},
            generated_at=now,
        )
        session.add(report)
        session.flush()
        session.add(
            DispatchTask(
                task_id="task_20260307_stale",
                report_id=report.id,
                sender_id="sender-stale",
                target_user="my_wechat_id",
                task_type="daily_report",
                payload={"message_chunks": ["日报正文"], "channel": "wechat"},
                status="dispatched",
                retry_count=1,
                max_retry=3,
                scheduled_at=now,
                dispatched_at=now - timedelta(minutes=10),
            )
        )
        session.commit()

    with Session(engine) as session:
        from app.services.dispatch_service import DispatchService
        from app.services.sender_service import upsert_sender_heartbeat
        from app.schemas.dispatch import SenderHeartbeatRequest

        reference_time = now.replace(microsecond=0)
        upsert_sender_heartbeat(
            session,
            SenderHeartbeatRequest(
                sender_id="sender-01",
                status="online",
                wechat_login_status="logged_in",
                timestamp=reference_time,
            ),
        )
        session.commit()

        service = DispatchService(session)
        service.settings = service.settings.model_copy(update={"dispatch_stale_timeout_seconds": 1})
        tasks = service.fetch_pending_tasks(sender_id="sender-01", limit=1)
        session.commit()

        assert len(tasks) == 1
        assert tasks[0].task_id == "task_20260307_stale"
        assert tasks[0].sender_id == "sender-01"
        assert tasks[0].status == "dispatched"
        assert tasks[0].last_error == "dispatch_timeout_recovered"

    with Session(engine) as session:
        task = session.query(DispatchTask).filter(DispatchTask.task_id == "task_20260307_stale").one()
        attempts = session.query(DispatchAttempt).filter(DispatchAttempt.dispatch_task_id == task.id).all()
        system_events = session.query(SystemEvent).filter(SystemEvent.object_id == task.task_id).all()

        assert task.retry_count == 2
        assert len(attempts) == 1
        assert attempts[0].error_code == "dispatch_timeout"
        assert attempts[0].retryable is True
        assert len(system_events) == 1
        assert system_events[0].event_type == "dispatch_timeout_recovered"


def test_admin_report_run_skips_when_report_and_dispatch_are_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    engine = build_sqlite_engine()
    settings = get_settings().model_copy(update={"candidate_event_limit_per_section": 10})
    app = create_app()

    def override_get_db():
        with Session(engine) as session:
            yield session

    def fake_run_collection_pipeline(*, session: Session, report_date: date | None = None):
        pipeline = CollectionPipeline(session=session, settings=settings, collectors=build_fixture_collectors())
        return pipeline.run(report_date=report_date)

    app.dependency_overrides[get_db] = override_get_db
    monkeypatch.setattr(scheduler_flow_module, "run_collection_pipeline", fake_run_collection_pipeline)

    try:
        with TestClient(app) as client:
            first_response = client.post(
                f"{API_PREFIX}/admin/report/run",
                headers={"Authorization": f"Bearer {settings.admin_token}"},
                json={"report_date": "2026-03-07"},
            )
            assert first_response.status_code == 200
            assert first_response.json()["data"]["status"] == "completed"

            second_response = client.post(
                f"{API_PREFIX}/admin/report/run",
                headers={"Authorization": f"Bearer {settings.admin_token}"},
                json={"report_date": "2026-03-07"},
            )
    finally:
        app.dependency_overrides.clear()

    assert second_response.status_code == 200
    second_body = second_response.json()
    assert second_body["data"]["status"] == "skipped"
    assert len(second_body["data"]["dispatch_task_ids"]) == 1
    report_date = date(2026, 3, 7)
    session = DummySession()
    calls: dict[str, object] = {}

    monkeypatch.setattr(scheduler_bootstrap, "get_session_factory", lambda: lambda: session)

    class FakeFlow:
        def __init__(self, flow_session) -> None:
            calls["session"] = flow_session

        def run(self, *, report_date=None, skip_send=False):
            calls["report_date"] = report_date
            calls["skip_send"] = skip_send
            return SimpleNamespace(
                job_id="job_report_run_20260307_test",
                report_generation=SimpleNamespace(
                    report=SimpleNamespace(report_date=report_date, generation_status="success"),
                    warnings=[],
                ),
                dispatch_task_ids=["task_1"],
                collection_warnings=[],
                report_reused=False,
                dispatch_created_count=1,
                dispatch_reused_count=0,
            )

    monkeypatch.setattr(scheduler_bootstrap, "SchedulerDispatchFlow", FakeFlow)

    scheduler_bootstrap.run_daily_dispatch_job(report_date=report_date, skip_send=True)

    assert calls["session"] is session
    assert calls["report_date"] == report_date
    assert calls["skip_send"] is True
    assert session.commit_called is True
    assert session.rollback_called is False
    assert session.closed is True


def test_run_daily_dispatch_job_rolls_back_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    session = DummySession()
    monkeypatch.setattr(scheduler_bootstrap, "get_session_factory", lambda: lambda: session)

    class FailingFlow:
        def __init__(self, flow_session) -> None:
            self.flow_session = flow_session

        def run(self, *, report_date=None, skip_send=False):
            raise RuntimeError("boom")

    monkeypatch.setattr(scheduler_bootstrap, "SchedulerDispatchFlow", FailingFlow)

    with pytest.raises(RuntimeError, match="boom"):
        scheduler_bootstrap.run_daily_dispatch_job(report_date=date(2026, 3, 7))

    assert session.commit_called is False
    assert session.rollback_called is True
    assert session.closed is True
