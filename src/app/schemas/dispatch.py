from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.db.enums import DispatchTaskStatus, GenerationStatus, ManualRunMode, SenderStatus, TaskResultStatus, WechatLoginStatus
SenderEventType = Literal[
    "wechat_logged_out",
    "wechat_window_not_found",
    "sender_process_error",
    "network_unavailable",
]
SenderEventLevel = Literal["info", "warning", "error"]


class ManualReportRunRequest(BaseModel):
    report_date: date | None = None
    mode: ManualRunMode = "manual"
    force_regenerate: bool = False
    skip_send: bool = False


class ManualReportRunResponse(BaseModel):
    job_id: str
    status: Literal["completed", "failed", "skipped"]
    report_date: date
    generation_status: GenerationStatus
    fallback_used: bool = False
    dispatch_task_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    last_error: str | None = None


class SenderHeartbeatRequest(BaseModel):
    sender_id: str
    status: SenderStatus
    wechat_login_status: WechatLoginStatus
    client_version: str | None = None
    host_name: str | None = None
    ip: str | None = None
    timestamp: datetime


class SenderHeartbeatResponse(BaseModel):
    server_time: datetime
    next_heartbeat_in_seconds: int = 30


class SenderTaskResultRequest(BaseModel):
    sender_id: str
    success: bool
    status: TaskResultStatus
    error_message: str | None = None
    retryable: bool = True
    sent_at: datetime
    detail: dict[str, Any] = Field(default_factory=dict)


class SenderEventRequest(BaseModel):
    sender_id: str
    event_type: SenderEventType
    level: SenderEventLevel = "warning"
    message: str
    occurred_at: datetime
    detail: dict[str, Any] = Field(default_factory=dict)


class PendingDispatchTaskPayload(BaseModel):
    task_id: str
    report_date: date
    task_type: str
    target_user: str
    message_chunks: list[str] = Field(default_factory=list)
    max_retry: int
    created_at: datetime


class ReportSectionDetail(BaseModel):
    section_key: str
    title: str
    content: str
    message_chunks: list[str] = Field(default_factory=list)
    render_mode: str = "template"


class DailyReportDetail(BaseModel):
    report_date: date
    generation_status: GenerationStatus
    fallback_used: bool
    full_text: str | None = None
    total_word_count: int | None = None
    total_message_chunks: int | None = None
    link_bundle: dict[str, Any] = Field(default_factory=dict)
    sections: list[ReportSectionDetail] = Field(default_factory=list)
    created_at: datetime
    generated_at: datetime | None = None
    last_error: str | None = None


class ContentMenuResponse(BaseModel):
    keyword: str
    title: str
    content: str
    message_chunks: list[str] = Field(default_factory=list)


class DispatchTaskDetail(BaseModel):
    task_id: str
    status: DispatchTaskStatus
    retry_count: int
    last_error: str | None = None
    sender_id: str | None = None
    scheduled_at: datetime
    sent_at: datetime | None = None


class SenderStatusDetail(BaseModel):
    sender_id: str
    status: SenderStatus
    wechat_login_status: WechatLoginStatus
    last_heartbeat_at: datetime | None = None
    is_healthy: bool
