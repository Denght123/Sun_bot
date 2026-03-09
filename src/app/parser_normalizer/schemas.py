from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class NormalizedRawItem(BaseModel):
    raw_item_id: int | None = None
    source_platform: str
    source_type: str
    external_id: str | None = None
    title: str
    summary: str | None = None
    url: str | None = None
    fallback_url: str | None = None
    published_at: datetime | None = None
    collected_at: datetime
    content_hash: str
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    language: str | None = "zh-CN"
    is_finance_related: bool = False
    finance_score: Decimal | None = None
    process_status: str = "pending"
    source_weight: Decimal = Decimal("0")
    heat_score: Decimal = Decimal("0")
    canonical_url: str | None = None


class ClassifiedItem(NormalizedRawItem):
    category: str = "overview"
    sub_category: str | None = None
