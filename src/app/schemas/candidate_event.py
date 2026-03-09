from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

CategoryKey = Literal["overview", "sector", "policy", "international", "risk", "hot_topic"]


class CandidateEvent(BaseModel):
    event_key: str
    title: str
    category: CategoryKey
    sub_category: str | None = None
    importance_score: Decimal
    heat_score: Decimal
    source_count: int
    source_links: list[str] = Field(default_factory=list)
    raw_item_ids: list[int] = Field(default_factory=list)
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None


class CandidateEventFeed(BaseModel):
    report_date: date
    window_start: datetime
    window_end: datetime
    sections: dict[CategoryKey, list[CandidateEvent]]


class PipelineRunRequest(BaseModel):
    report_date: date | None = None


class PipelineRunResult(BaseModel):
    report_date: date
    window_start: datetime
    window_end: datetime
    sources: list[str] = Field(default_factory=list)
    collected_count: int
    inserted_count: int
    window_item_count: int
    finance_item_count: int
    cluster_count: int
    warnings: list[str] = Field(default_factory=list)
    candidate_feed: CandidateEventFeed
