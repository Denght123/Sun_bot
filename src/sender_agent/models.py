from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

SenderStatus = Literal["online", "offline", "degraded"]
WechatLoginStatus = Literal["logged_in", "logged_out", "unknown"]
TaskResultStatus = Literal["sent", "failed", "partial"]
SenderEventType = Literal[
    "wechat_logged_out",
    "wechat_window_not_found",
    "sender_process_error",
    "network_unavailable",
]
SenderEventLevel = Literal["info", "warning", "error"]
JournalTaskStatus = Literal[
    "claimed",
    "sending",
    "sent_local",
    "result_pending",
    "result_confirmed",
    "failed_local",
]


class ResponseEnvelope(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any = None


class SenderHeartbeatPayload(BaseModel):
    sender_id: str
    status: SenderStatus
    wechat_login_status: WechatLoginStatus
    client_version: str | None = None
    host_name: str | None = None
    ip: str | None = None
    timestamp: datetime


class SenderHeartbeatResponseData(BaseModel):
    server_time: datetime
    next_heartbeat_in_seconds: int = 30


class PendingDispatchTask(BaseModel):
    task_id: str
    report_date: date
    task_type: str
    target_user: str
    message_chunks: list[str] = Field(default_factory=list)
    max_retry: int = 3
    created_at: datetime

    @property
    def chunk_count(self) -> int:
        return len(self.message_chunks)


class PendingDispatchTasksData(BaseModel):
    tasks: list[PendingDispatchTask] = Field(default_factory=list)


class SenderTaskResultPayload(BaseModel):
    sender_id: str
    success: bool
    status: TaskResultStatus
    error_message: str | None = None
    retryable: bool = True
    sent_at: datetime
    detail: dict[str, Any] = Field(default_factory=dict)


class SenderTaskResultResponseData(BaseModel):
    task_status: str


class SenderEventPayload(BaseModel):
    sender_id: str
    event_type: SenderEventType
    level: SenderEventLevel = "warning"
    message: str
    occurred_at: datetime
    detail: dict[str, Any] = Field(default_factory=dict)


class ContentMenuPayload(BaseModel):
    keyword: str
    title: str
    content: str
    message_chunks: list[str] = Field(default_factory=list)


class JournalRecord(BaseModel):
    task_id: str
    target_user: str
    task_type: str
    status: JournalTaskStatus
    sent_chunks: int = 0
    last_error: str | None = None
    result_payload: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime
    result_confirmed_at: datetime | None = None
