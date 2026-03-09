from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.model_definitions import DispatchAttempt, EventCluster, RawItem, SystemEvent
from app.db.repositories import DispatchTaskRepository, EventClusterRepository, RawItemRepository, SenderRepository, SystemEventRepository
from app.parser_normalizer.schemas import NormalizedRawItem
from app.rule_engine.clusterer import ClusteredEvent


def build_sqlite_engine():
    return create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )


def test_repository_round_trip_for_mvp_tables() -> None:
    engine = build_sqlite_engine()
    Base.metadata.create_all(engine)
    now = datetime(2026, 3, 8, 8, 0, tzinfo=timezone.utc)

    with Session(engine) as session:
        raw_items = RawItemRepository(session)
        event_clusters = EventClusterRepository(session)
        dispatch_tasks = DispatchTaskRepository(session)
        senders = SenderRepository(session)

        raw_item, created = raw_items.upsert(
            NormalizedRawItem(
                source_platform="cls",
                source_type="finance",
                external_id="telegraph-1",
                title="央行发布新政策",
                summary="摘要",
                url="https://example.com/a",
                fallback_url="https://example.com/search/a",
                collected_at=now,
                content_hash="hash-1",
                raw_payload={"source": "fixture"},
                process_status="pending",
            )
        )
        assert created is True
        assert raw_item.id is not None

        updated = raw_items.update_processing(
            raw_item_id=raw_item.id,
            is_finance_related=True,
            finance_score=Decimal("8.50"),
            process_status="processed",
        )
        assert updated is not None
        assert updated.process_status == "processed"

        cluster = event_clusters.create(
            ClusteredEvent(
                event_key="event-20260308-001",
                title="央行发布新政策",
                category="policy",
                sub_category=None,
                importance_score=Decimal("7.80"),
                heat_score=Decimal("3.20"),
                source_count=1,
                first_seen_at=None,
                last_seen_at=None,
                cluster_date=date(2026, 3, 8),
                status="active",
                items=[],
            )
        )
        event_clusters.add_source(cluster_id=cluster.id, raw_item_id=raw_item.id, source_weight=Decimal("1.00"))

        sender = senders.upsert_heartbeat(
            sender_id="sender-01",
            status="online",
            wechat_login_status="logged_in",
            reported_at=raw_item.collected_at,
            client_version="0.1.0",
            host_name="host-01",
            current_ip="127.0.0.1",
            payload={"sender_id": "sender-01"},
        )
        assert sender.id is not None

        from app.db.model_definitions import DailyReport, ReportSection

        report = DailyReport(
            report_date=date(2026, 3, 8),
            generation_status="success",
            fallback_used=False,
            data_window_start=raw_item.collected_at,
            data_window_end=raw_item.collected_at,
            total_word_count=100,
            total_message_chunks=1,
            full_text="日报正文",
            link_bundle={"message_chunks": ["日报正文"]},
        )
        session.add(report)
        session.flush()

        session.add(
            ReportSection(
                report_id=report.id,
                section_key="policy",
                title="政策动态",
                content="政策内容",
                message_chunks=["政策内容"],
                sort_order=1,
            )
        )
        session.flush()

        task = dispatch_tasks.create(
            task_id="task_20260308_test",
            report_id=report.id,
            sender_id=sender.sender_id,
            target_user="my_wechat_id",
            task_type="daily_report",
            payload={"message_chunks": ["日报正文"], "full_text": "日报正文"},
            status="pending",
            retry_count=0,
            max_retry=3,
            scheduled_at=raw_item.collected_at,
        )
        assert task.id is not None

        attempt = dispatch_tasks.create_attempt(
            dispatch_task_id=task.id,
            attempt_no=1,
            sender_id=sender.sender_id,
            status="success",
            error_code=None,
            error_message=None,
            retryable=False,
            started_at=raw_item.collected_at,
            finished_at=raw_item.collected_at,
        )
        assert attempt.id is not None

        failure_attempt = dispatch_tasks.create_attempt(
            dispatch_task_id=task.id,
            attempt_no=2,
            sender_id=sender.sender_id,
            status="failed",
            error_code="wechat_partial_send",
            error_message="partial send",
            retryable=False,
            started_at=raw_item.collected_at,
            finished_at=raw_item.collected_at,
        )
        assert failure_attempt.error_code == "wechat_partial_send"

        system_event = SystemEventRepository(session).create(
            event_type="dispatch_partial_send",
            level="warning",
            object_type="dispatch_task",
            object_id=task.task_id,
            message="Sender reported partial send",
            detail={"attempt_no": 2, "error_code": "wechat_partial_send"},
            occurred_at=raw_item.collected_at,
        )
        assert system_event.id is not None

        raw_item_id = raw_item.id
        cluster_id = cluster.id
        task_id = task.id
        system_event_id = system_event.id
        session.commit()

    with Session(engine) as session:
        assert session.get(RawItem, raw_item_id) is not None
        assert session.get(EventCluster, cluster_id) is not None
        persisted_task = DispatchTaskRepository(session).get_by_task_id("task_20260308_test")
        assert persisted_task is not None
        attempts = session.query(DispatchAttempt).filter(DispatchAttempt.dispatch_task_id == task_id).order_by(DispatchAttempt.attempt_no).all()
        assert len(attempts) == 2
        assert attempts[1].error_code == "wechat_partial_send"
        assert session.get(SystemEvent, system_event_id) is not None
        assert SenderRepository(session).get_by_business_id("sender-01") is not None
