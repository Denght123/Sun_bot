from __future__ import annotations

from pydantic import BaseModel


class DependencyStatus(BaseModel):
    ok: bool
    detail: str | None = None


class LiveStatus(BaseModel):
    status: str
    service: str
    environment: str
    timezone: str


class ReadinessStatus(BaseModel):
    status: str
    service: str
    environment: str
    timezone: str
    database: DependencyStatus
    redis: DependencyStatus
