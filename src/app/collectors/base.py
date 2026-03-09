from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import requests

from app.core.config import Settings, get_settings


@dataclass(slots=True)
class CollectedItem:
    source_platform: str
    source_type: str
    title: str
    external_id: str | None = None
    summary: str | None = None
    url: str | None = None
    fallback_url: str | None = None
    published_at: datetime | str | int | float | None = None
    collected_at: datetime | str | int | float | None = None
    language: str | None = "zh-CN"
    raw_payload: dict[str, Any] = field(default_factory=dict)


class BaseCollector(ABC):
    source_platform: str
    source_type: str

    def __init__(self, settings: Settings | None = None, session: requests.Session | None = None) -> None:
        self.settings = settings or get_settings()
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": self.settings.collector_user_agent})

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        timeout = kwargs.pop("timeout", self.settings.collector_request_timeout_seconds)
        response = self.session.get(url, timeout=timeout, **kwargs)
        response.raise_for_status()
        return response

    @abstractmethod
    def collect(self) -> list[CollectedItem]:
        raise NotImplementedError
