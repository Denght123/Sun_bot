from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


class SenderAgentError(Exception):
    pass


class SenderConfigError(SenderAgentError):
    pass


class SenderApiError(SenderAgentError):
    def __init__(self, message: str, *, code: int | None = None, status_code: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


class SenderNetworkError(SenderAgentError):
    pass


class SenderRetryableError(SenderAgentError):
    pass


class WechatAutomationError(SenderAgentError):
    pass


class WechatUnavailableError(WechatAutomationError):
    pass


class WechatLoggedOutError(WechatUnavailableError):
    pass


class WechatWindowNotFoundError(WechatUnavailableError):
    pass


class WechatChatNotFoundError(WechatAutomationError):
    pass


class WechatPartialSendError(WechatAutomationError):
    def __init__(self, message: str, *, sent_chunks: int) -> None:
        super().__init__(message)
        self.sent_chunks = sent_chunks


@dataclass(slots=True)
class PendingResultReport:
    task_id: str
    payload: dict[str, object]
    recorded_at: datetime
