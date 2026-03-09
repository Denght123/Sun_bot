from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import delete, or_, select
from sqlalchemy.orm import Session

from app.db.model_definitions import DispatchAttempt, DispatchTask, EventCluster, EventSource, RawItem, Sender, SenderHeartbeat, SystemEvent
from app.parser_normalizer.schemas import NormalizedRawItem
from app.rule_engine.clusterer import ClusteredEvent


class RawItemRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, raw_item_id: int) -> RawItem | None:
        return self.session.get(RawItem, raw_item_id)

    def find_existing(self, item: NormalizedRawItem) -> RawItem | None:
        if item.external_id:
            existing = self.session.scalar(
                select(RawItem).where(
                    RawItem.source_platform == item.source_platform,
                    RawItem.external_id == item.external_id,
                )
            )
            if existing is not None:
                return existing
        if item.canonical_url:
            existing = self.session.scalar(select(RawItem).where(RawItem.url == item.canonical_url))
            if existing is not None:
                return existing
        return self.session.scalar(select(RawItem).where(RawItem.content_hash == item.content_hash))

    def upsert(self, item: NormalizedRawItem) -> tuple[RawItem, bool]:
        existing = self.find_existing(item)
        if existing is None:
            model = RawItem(
                source_platform=item.source_platform,
                source_type=item.source_type,
                external_id=item.external_id,
                title=item.title,
                summary=item.summary,
                url=item.url,
                fallback_url=item.fallback_url,
                published_at=item.published_at,
                collected_at=item.collected_at,
                content_hash=item.content_hash,
                raw_payload=item.raw_payload,
                language=item.language,
                is_finance_related=item.is_finance_related,
                finance_score=item.finance_score,
                process_status=item.process_status,
            )
            self.session.add(model)
            self.session.flush()
            return model, True

        existing.title = item.title
        existing.summary = item.summary
        existing.url = item.url
        existing.fallback_url = item.fallback_url
        existing.published_at = item.published_at
        existing.collected_at = item.collected_at
        existing.raw_payload = item.raw_payload
        existing.language = item.language
        existing.content_hash = item.content_hash
        self.session.flush()
        return existing, False

    def update_processing(
        self,
        *,
        raw_item_id: int,
        is_finance_related: bool,
        finance_score: Decimal | None,
        process_status: str,
    ) -> RawItem | None:
        model = self.get(raw_item_id)
        if model is None:
            return None
        model.is_finance_related = is_finance_related
        model.finance_score = finance_score
        model.process_status = process_status
        self.session.flush()
        return model


class EventClusterRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_ids_by_date(self, cluster_date: date) -> list[int]:
        return list(self.session.scalars(select(EventCluster.id).where(EventCluster.cluster_date == cluster_date)))

    def clear_for_date(self, cluster_date: date) -> None:
        cluster_ids = self.list_ids_by_date(cluster_date)
        if not cluster_ids:
            return
        self.session.execute(delete(EventSource).where(EventSource.cluster_id.in_(cluster_ids)))
        self.session.execute(delete(EventCluster).where(EventCluster.id.in_(cluster_ids)))
        self.session.flush()

    def create(self, cluster: ClusteredEvent) -> EventCluster:
        cluster_model = EventCluster(
            event_key=cluster.event_key,
            title=cluster.title,
            category=cluster.category,
            sub_category=cluster.sub_category,
            importance_score=cluster.importance_score,
            heat_score=cluster.heat_score,
            source_count=cluster.source_count,
            first_seen_at=cluster.first_seen_at,
            last_seen_at=cluster.last_seen_at,
            cluster_date=cluster.cluster_date,
            status=cluster.status,
        )
        self.session.add(cluster_model)
        self.session.flush()
        return cluster_model

    def add_source(self, *, cluster_id: int, raw_item_id: int, source_weight: Decimal | None) -> EventSource:
        source = EventSource(cluster_id=cluster_id, raw_item_id=raw_item_id, source_weight=source_weight)
        self.session.add(source)
        self.session.flush()
        return source


class DispatchTaskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_task_id(self, task_id: str) -> DispatchTask | None:
        return self.session.scalar(select(DispatchTask).where(DispatchTask.task_id == task_id))

    def find_active_by_report(self, *, report_id: int, task_type: str) -> list[DispatchTask]:
        return self.session.scalars(
            select(DispatchTask).where(
                DispatchTask.report_id == report_id,
                DispatchTask.task_type == task_type,
                DispatchTask.status != "cancelled",
            )
        ).all()

    def create(
        self,
        *,
        task_id: str,
        report_id: int,
        sender_id: str | None,
        target_user: str,
        task_type: str,
        payload: dict[str, object],
        status: str,
        retry_count: int,
        max_retry: int,
        scheduled_at: datetime,
    ) -> DispatchTask:
        task = DispatchTask(
            task_id=task_id,
            report_id=report_id,
            sender_id=sender_id,
            target_user=target_user,
            task_type=task_type,
            payload=payload,
            status=status,
            retry_count=retry_count,
            max_retry=max_retry,
            scheduled_at=scheduled_at,
        )
        self.session.add(task)
        self.session.flush()
        return task

    def list_pending_for_sender(self, *, sender_id: str, limit: int) -> list[DispatchTask]:
        return self.session.scalars(
            select(DispatchTask)
            .where(
                DispatchTask.status.in_(["pending", "waiting_sender"]),
                or_(DispatchTask.sender_id.is_(None), DispatchTask.sender_id == sender_id),
            )
            .order_by(DispatchTask.scheduled_at, DispatchTask.created_at)
            .limit(max(1, min(limit, 10)))
        ).all()

    def create_attempt(
        self,
        *,
        dispatch_task_id: int,
        attempt_no: int,
        sender_id: str | None,
        status: str,
        error_code: str | None,
        error_message: str | None,
        retryable: bool,
        started_at: datetime | None,
        finished_at: datetime | None,
    ) -> DispatchAttempt:
        attempt = DispatchAttempt(
            dispatch_task_id=dispatch_task_id,
            attempt_no=attempt_no,
            sender_id=sender_id,
            status=status,
            error_code=error_code,
            error_message=error_message,
            retryable=retryable,
            started_at=started_at,
            finished_at=finished_at,
        )
        self.session.add(attempt)
        self.session.flush()
        return attempt

    def release_stale_tasks(self, *, stale_before: datetime) -> list[DispatchTask]:
        return self.session.scalars(
            select(DispatchTask).where(
                DispatchTask.status.in_(["dispatched", "sending"]),
                DispatchTask.dispatched_at.is_not(None),
                DispatchTask.dispatched_at <= stale_before,
            )
        ).all()


class SystemEventRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        event_type: str,
        level: str,
        object_type: str | None,
        object_id: str | None,
        message: str,
        detail: dict[str, object] | None,
        occurred_at: datetime,
    ) -> SystemEvent:
        event = SystemEvent(
            event_type=event_type,
            level=level,
            object_type=object_type,
            object_id=object_id,
            message=message,
            detail=detail,
            occurred_at=occurred_at,
        )
        self.session.add(event)
        self.session.flush()
        return event


class SenderRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_business_id(self, sender_id: str) -> Sender | None:
        return self.session.scalar(select(Sender).where(Sender.sender_id == sender_id))

    def list_by_last_heartbeat(self) -> list[Sender]:
        return self.session.scalars(select(Sender).order_by(Sender.last_heartbeat_at.desc().nullslast())).all()

    def upsert_heartbeat(
        self,
        *,
        sender_id: str,
        status: str,
        wechat_login_status: str,
        reported_at: datetime,
        client_version: str | None = None,
        host_name: str | None = None,
        current_ip: str | None = None,
        payload: dict[str, object] | None = None,
    ) -> Sender:
        sender = self.get_by_business_id(sender_id)
        if sender is None:
            sender = Sender(sender_id=sender_id)
            self.session.add(sender)
            self.session.flush()

        sender.status = status
        sender.wechat_login_status = wechat_login_status
        sender.host_name = host_name
        sender.current_ip = current_ip
        sender.client_version = client_version
        sender.last_heartbeat_at = reported_at

        self.session.add(
            SenderHeartbeat(
                sender_row_id=sender.id,
                status=status,
                wechat_login_status=wechat_login_status,
                payload=payload,
                reported_at=reported_at,
            )
        )
        self.session.flush()
        return sender
