from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256

from app.parser_normalizer.schemas import ClassifiedItem
from app.rule_engine.dedup import keyword_overlap, normalize_title_for_match, title_similarity


@dataclass(slots=True)
class ClusteredEvent:
    event_key: str
    title: str
    category: str
    sub_category: str | None
    importance_score: Decimal
    heat_score: Decimal
    source_count: int
    first_seen_at: datetime | None
    last_seen_at: datetime | None
    cluster_date: date
    status: str
    items: list[ClassifiedItem]


@dataclass(slots=True)
class _ClusterAccumulator:
    items: list[ClassifiedItem]

    def add(self, item: ClassifiedItem) -> None:
        self.items.append(item)

    @property
    def title_item(self) -> ClassifiedItem:
        return sorted(
            self.items,
            key=lambda item: (
                item.source_platform != "cls",
                -(item.heat_score or Decimal("0")),
                -len(item.title),
            ),
        )[0]

    @property
    def representative_titles(self) -> list[str]:
        return [item.title for item in self.items]


def cluster_items(items: list[ClassifiedItem], report_date: date) -> list[ClusteredEvent]:
    ordered_items = sorted(items, key=lambda item: item.published_at or item.collected_at)
    accumulators: list[_ClusterAccumulator] = []

    for item in ordered_items:
        matched = next((cluster for cluster in accumulators if is_same_event(cluster, item)), None)
        if matched is None:
            accumulators.append(_ClusterAccumulator(items=[item]))
        else:
            matched.add(item)

    clustered = [build_clustered_event(cluster, report_date) for cluster in accumulators]
    return sorted(clustered, key=lambda event: (event.importance_score, event.heat_score, event.source_count), reverse=True)


def is_same_event(cluster: _ClusterAccumulator, item: ClassifiedItem) -> bool:
    candidate_url = item.canonical_url or item.url or item.fallback_url
    if candidate_url:
        for existing in cluster.items:
            existing_url = existing.canonical_url or existing.url or existing.fallback_url
            if existing_url and existing_url == candidate_url:
                return True

    normalized_title = normalize_title_for_match(item.title)
    for existing_title in cluster.representative_titles:
        if normalized_title and normalized_title == normalize_title_for_match(existing_title):
            return True
        if title_similarity(item.title, existing_title) >= 0.78:
            return True
        if keyword_overlap(item.title, existing_title) >= 0.72 and is_time_close(item, cluster.title_item):
            return True
    return False


def is_time_close(left: ClassifiedItem, right: ClassifiedItem) -> bool:
    left_time = left.published_at or left.collected_at
    right_time = right.published_at or right.collected_at
    if left_time is None or right_time is None:
        return True
    return abs((left_time - right_time).total_seconds()) <= 6 * 3600


def build_clustered_event(cluster: _ClusterAccumulator, report_date: date) -> ClusteredEvent:
    title_item = cluster.title_item
    items = cluster.items
    first_seen_at = min((item.published_at or item.collected_at for item in items), default=None)
    last_seen_at = max((item.published_at or item.collected_at for item in items), default=None)
    heat_score = max((item.heat_score for item in items), default=Decimal("0"))
    importance_score = compute_importance_score(items, heat_score, last_seen_at)
    event_key = build_event_key(report_date, title_item, items)
    return ClusteredEvent(
        event_key=event_key,
        title=title_item.title,
        category=title_item.category,
        sub_category=title_item.sub_category,
        importance_score=importance_score,
        heat_score=heat_score,
        source_count=len(items),
        first_seen_at=first_seen_at,
        last_seen_at=last_seen_at,
        cluster_date=report_date,
        status="active",
        items=items,
    )


def compute_importance_score(items: list[ClassifiedItem], heat_score: Decimal, last_seen_at: datetime | None) -> Decimal:
    finance_score = max((item.finance_score or Decimal("0") for item in items), default=Decimal("0"))
    source_weight = sum((item.source_weight for item in items), start=Decimal("0"))
    source_count_bonus = Decimal(str(min(len(items) * 0.6, 3.0)))
    heat_bonus = normalize_heat_bonus(heat_score)
    recency_bonus = Decimal("0")
    if last_seen_at is not None:
        recency_bonus = Decimal("1.20") if last_seen_at.hour < 8 else Decimal("0.60")
    total = finance_score + source_weight + source_count_bonus + heat_bonus + recency_bonus
    return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def normalize_heat_bonus(heat_score: Decimal) -> Decimal:
    if heat_score >= Decimal("100000000"):
        return Decimal("5.00")
    if heat_score >= Decimal("10000000"):
        return Decimal("4.00")
    if heat_score >= Decimal("1000000"):
        return Decimal("3.00")
    if heat_score >= Decimal("100000"):
        return Decimal("2.00")
    if heat_score > 0:
        return Decimal("1.00")
    return Decimal("0.00")


def build_event_key(report_date: date, title_item: ClassifiedItem, items: list[ClassifiedItem]) -> str:
    canonical_url = next((item.canonical_url or item.url or item.fallback_url for item in items if item.canonical_url or item.url or item.fallback_url), None)
    seed_parts = [report_date.isoformat(), canonical_url or normalize_title_for_match(title_item.title)]
    member_ids = sorted(str(item.raw_item_id or item.external_id or item.title) for item in items)
    seed_parts.extend(member_ids)
    digest = sha256("|".join(seed_parts).encode("utf-8")).hexdigest()[:20]
    return f"event-{report_date.strftime('%Y%m%d')}-{digest}"
