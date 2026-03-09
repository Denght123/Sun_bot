from __future__ import annotations

from collections import defaultdict

from app.rule_engine.clusterer import ClusteredEvent
from app.schemas.candidate_event import CandidateEvent, CandidateEventFeed

SECTION_ORDER = ("overview", "sector", "policy", "international", "risk", "hot_topic")


def build_candidate_event_feed(*, report_date, window_start, window_end, clusters: list[ClusteredEvent], limit_per_section: int) -> CandidateEventFeed:
    grouped: dict[str, list[CandidateEvent]] = defaultdict(list)

    for cluster in clusters:
        grouped[cluster.category].append(
            CandidateEvent(
                event_key=cluster.event_key,
                title=cluster.title,
                category=cluster.category,
                sub_category=cluster.sub_category,
                importance_score=cluster.importance_score,
                heat_score=cluster.heat_score,
                source_count=cluster.source_count,
                source_links=_source_links(cluster),
                raw_item_ids=_raw_item_ids(cluster),
                first_seen_at=cluster.first_seen_at,
                last_seen_at=cluster.last_seen_at,
            )
        )

    sections = {section: grouped.get(section, [])[:limit_per_section] for section in SECTION_ORDER}
    return CandidateEventFeed(
        report_date=report_date,
        window_start=window_start,
        window_end=window_end,
        sections=sections,
    )


def _source_links(cluster: ClusteredEvent) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for item in cluster.items:
        for candidate in (item.url, item.fallback_url):
            if candidate and candidate not in seen:
                seen.add(candidate)
                links.append(candidate)
    return links


def _raw_item_ids(cluster: ClusteredEvent) -> list[int]:
    return [item.raw_item_id for item in cluster.items if item.raw_item_id is not None]
