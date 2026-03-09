from __future__ import annotations

from enum import StrEnum


class ManualRunMode(StrEnum):
    MANUAL = "manual"
    RETRY = "retry"


class RawItemProcessStatus(StrEnum):
    PENDING = "pending"
    PROCESSED = "processed"
    FILTERED = "filtered"


class EventClusterStatus(StrEnum):
    ACTIVE = "active"
    DROPPED = "dropped"


class EventCategory(StrEnum):
    OVERVIEW = "overview"
    SECTOR = "sector"
    POLICY = "policy"
    INTERNATIONAL = "international"
    RISK = "risk"
    HOT_TOPIC = "hot_topic"


class ReportSectionKey(StrEnum):
    OVERVIEW = "overview"
    SECTOR = "sector"
    POLICY = "policy"
    INTERNATIONAL = "international"
    HOT_TOPICS = "hot_topics"
    RISK = "risk"
    HELP = "help"


class GenerationStatus(StrEnum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    FALLBACK_SUCCESS = "fallback_success"


class DispatchTaskType(StrEnum):
    DAILY_REPORT = "daily_report"
    KEYWORD_REPLY = "keyword_reply"
    MANUAL_RESEND = "manual_resend"


class DispatchTaskStatus(StrEnum):
    PENDING = "pending"
    DISPATCHED = "dispatched"
    SENDING = "sending"
    SENT = "sent"
    FAILED = "failed"
    WAITING_SENDER = "waiting_sender"
    CANCELLED = "cancelled"


class DispatchAttemptStatus(StrEnum):
    SUCCESS = "success"
    FAILED = "failed"


class SenderStatus(StrEnum):
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"


class WechatLoginStatus(StrEnum):
    LOGGED_IN = "logged_in"
    LOGGED_OUT = "logged_out"
    UNKNOWN = "unknown"


class TaskResultStatus(StrEnum):
    SENT = "sent"
    FAILED = "failed"
    PARTIAL = "partial"


SECTION_KEY_ALIAS_MAP: dict[str, str] = {
    EventCategory.OVERVIEW.value: ReportSectionKey.OVERVIEW.value,
    EventCategory.SECTOR.value: ReportSectionKey.SECTOR.value,
    EventCategory.POLICY.value: ReportSectionKey.POLICY.value,
    EventCategory.INTERNATIONAL.value: ReportSectionKey.INTERNATIONAL.value,
    EventCategory.RISK.value: ReportSectionKey.RISK.value,
    EventCategory.HOT_TOPIC.value: ReportSectionKey.HOT_TOPICS.value,
    ReportSectionKey.HOT_TOPICS.value: ReportSectionKey.HOT_TOPICS.value,
}

KEYWORD_SECTION_KEY_MAP: dict[str, str] = {
    "板块": ReportSectionKey.SECTOR.value,
    "政策": ReportSectionKey.POLICY.value,
    "国际": ReportSectionKey.INTERNATIONAL.value,
    "热搜": ReportSectionKey.HOT_TOPICS.value,
    "风险": ReportSectionKey.RISK.value,
}

CORE_MVP_TABLES: tuple[str, ...] = (
    "raw_items",
    "event_clusters",
    "daily_reports",
    "report_sections",
    "dispatch_tasks",
    "dispatch_attempts",
    "senders",
    "sender_heartbeats",
    "system_events",
)
