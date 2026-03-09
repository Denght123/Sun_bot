from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.enums import (
    DispatchAttemptStatus,
    DispatchTaskStatus,
    EventClusterStatus,
    GenerationStatus,
    RawItemProcessStatus,
    SenderStatus,
    WechatLoginStatus,
)

BIGINT_PK = BigInteger().with_variant(Integer, "sqlite")
JSON_PAYLOAD = JSON().with_variant(JSONB, "postgresql")


class RawItem(Base):
    __tablename__ = "raw_items"
    __table_args__ = (
        UniqueConstraint("source_platform", "external_id", name="uk_raw_items_source_platform_external_id"),
        Index("idx_raw_items_source_platform_collected_at", "source_platform", "collected_at"),
        Index("idx_raw_items_content_hash", "content_hash"),
        Index("idx_raw_items_is_finance_related", "is_finance_related"),
        Index("idx_raw_items_published_at", "published_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    source_platform: Mapped[str] = mapped_column(String(50), nullable=False)
    source_type: Mapped[str] = mapped_column(String(20), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(128))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(Text)
    fallback_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSON_PAYLOAD)
    language: Mapped[str | None] = mapped_column(String(10))
    is_finance_related: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    finance_score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    process_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=RawItemProcessStatus.PENDING.value,
        server_default=RawItemProcessStatus.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    event_sources: Mapped[list[EventSource]] = relationship(back_populates="raw_item", cascade="all, delete-orphan")


class EventCluster(Base):
    __tablename__ = "event_clusters"
    __table_args__ = (
        UniqueConstraint("event_key", name="uk_event_clusters_event_key"),
        Index("idx_event_clusters_cluster_date_category", "cluster_date", "category"),
        Index("idx_event_clusters_importance_score", "importance_score"),
        Index("idx_event_clusters_last_seen_at", "last_seen_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    event_key: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    sub_category: Mapped[str | None] = mapped_column(String(50))
    importance_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=0, server_default="0")
    heat_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=0, server_default="0")
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    first_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cluster_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=EventClusterStatus.ACTIVE.value,
        server_default=EventClusterStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    sources: Mapped[list[EventSource]] = relationship(back_populates="cluster", cascade="all, delete-orphan")


class EventSource(Base):
    __tablename__ = "event_sources"
    __table_args__ = (
        UniqueConstraint("cluster_id", "raw_item_id", name="uk_event_sources_cluster_id_raw_item_id"),
        Index("idx_event_sources_cluster_id", "cluster_id"),
        Index("idx_event_sources_raw_item_id", "raw_item_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("event_clusters.id", ondelete="CASCADE"), nullable=False)
    raw_item_id: Mapped[int] = mapped_column(ForeignKey("raw_items.id", ondelete="CASCADE"), nullable=False)
    source_weight: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    cluster: Mapped[EventCluster] = relationship(back_populates="sources")
    raw_item: Mapped[RawItem] = relationship(back_populates="event_sources")


class DailyReport(Base):
    __tablename__ = "daily_reports"
    __table_args__ = (
        UniqueConstraint("report_date", name="uk_daily_reports_report_date"),
        Index("idx_daily_reports_generation_status", "generation_status"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    generation_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=GenerationStatus.PENDING.value,
        server_default=GenerationStatus.PENDING.value,
    )
    fallback_used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    data_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    data_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    total_word_count: Mapped[int | None] = mapped_column(Integer)
    total_message_chunks: Mapped[int | None] = mapped_column(Integer)
    full_text: Mapped[str | None] = mapped_column(Text)
    link_bundle: Mapped[dict | None] = mapped_column(JSON_PAYLOAD)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    sections: Mapped[list[ReportSection]] = relationship(back_populates="report", cascade="all, delete-orphan")
    dispatch_tasks: Mapped[list[DispatchTask]] = relationship(back_populates="report", cascade="all, delete-orphan")


class ReportSection(Base):
    __tablename__ = "report_sections"
    __table_args__ = (
        UniqueConstraint("report_id", "section_key", name="uk_report_sections_report_id_section_key"),
        Index("idx_report_sections_report_id", "report_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    report_id: Mapped[int] = mapped_column(ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=False)
    section_key: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_chunks: Mapped[list[str] | None] = mapped_column(JSON_PAYLOAD)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    report: Mapped[DailyReport] = relationship(back_populates="sections")


class DispatchTask(Base):
    __tablename__ = "dispatch_tasks"
    __table_args__ = (
        UniqueConstraint("task_id", name="uk_dispatch_tasks_task_id"),
        Index("idx_dispatch_tasks_status_scheduled_at", "status", "scheduled_at"),
        Index("idx_dispatch_tasks_sender_id", "sender_id"),
        Index("idx_dispatch_tasks_report_id", "report_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(String(64), nullable=False)
    report_id: Mapped[int] = mapped_column(ForeignKey("daily_reports.id", ondelete="CASCADE"), nullable=False)
    sender_id: Mapped[str | None] = mapped_column(String(64))
    target_user: Mapped[str] = mapped_column(String(128), nullable=False)
    task_type: Mapped[str] = mapped_column(String(30), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON_PAYLOAD, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=DispatchTaskStatus.PENDING.value,
        server_default=DispatchTaskStatus.PENDING.value,
    )
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    max_retry: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    report: Mapped[DailyReport] = relationship(back_populates="dispatch_tasks")
    attempts: Mapped[list[DispatchAttempt]] = relationship(back_populates="task", cascade="all, delete-orphan")


class DispatchAttempt(Base):
    __tablename__ = "dispatch_attempts"
    __table_args__ = (
        UniqueConstraint("task_id", "attempt_no", name="uk_dispatch_attempts_task_id_attempt_no"),
        Index("idx_dispatch_attempts_task_id", "task_id"),
        Index("idx_dispatch_attempts_sender_id", "sender_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    dispatch_task_id: Mapped[int] = mapped_column("task_id", ForeignKey("dispatch_tasks.id", ondelete="CASCADE"), nullable=False)
    attempt_no: Mapped[int] = mapped_column(Integer, nullable=False)
    sender_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=DispatchAttemptStatus.FAILED.value,
        server_default=DispatchAttemptStatus.FAILED.value,
    )
    error_code: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    task: Mapped[DispatchTask] = relationship(back_populates="attempts")


class Sender(Base):
    __tablename__ = "senders"
    __table_args__ = (
        UniqueConstraint("sender_id", name="uk_senders_sender_id"),
        Index("idx_senders_status", "status"),
        Index("idx_senders_last_heartbeat_at", "last_heartbeat_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    sender_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sender_name: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=SenderStatus.OFFLINE.value,
        server_default=SenderStatus.OFFLINE.value,
    )
    wechat_login_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=WechatLoginStatus.UNKNOWN.value,
        server_default=WechatLoginStatus.UNKNOWN.value,
    )
    host_name: Mapped[str | None] = mapped_column(String(100))
    current_ip: Mapped[str | None] = mapped_column(String(64))
    client_version: Mapped[str | None] = mapped_column(String(50))
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    token_hash: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    heartbeats: Mapped[list[SenderHeartbeat]] = relationship(back_populates="sender", cascade="all, delete-orphan")


class SenderHeartbeat(Base):
    __tablename__ = "sender_heartbeats"
    __table_args__ = (
        Index("idx_sender_heartbeats_sender_id_reported_at", "sender_id", "reported_at"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    sender_row_id: Mapped[int] = mapped_column("sender_id", ForeignKey("senders.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    wechat_login_status: Mapped[str] = mapped_column(String(20), nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSON_PAYLOAD)
    reported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    sender: Mapped[Sender] = relationship(back_populates="heartbeats")


class SystemEvent(Base):
    __tablename__ = "system_events"
    __table_args__ = (
        Index("idx_system_events_event_type", "event_type"),
        Index("idx_system_events_level_occurred_at", "level", "occurred_at"),
        Index("idx_system_events_object_type_object_id", "object_type", "object_id"),
    )

    id: Mapped[int] = mapped_column(BIGINT_PK, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    object_type: Mapped[str | None] = mapped_column(String(50))
    object_id: Mapped[str | None] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict | None] = mapped_column(JSON_PAYLOAD)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


def build_message_chunks_from_payload(payload: dict | None) -> Sequence[str]:
    if not payload:
        return []
    chunks = payload.get("message_chunks")
    if not isinstance(chunks, list):
        return []
    return [str(chunk) for chunk in chunks if isinstance(chunk, str)]
