from __future__ import annotations

from collections import defaultdict

from app.reports.contracts import DETAIL_SECTION_LIMITS, FULL_REPORT_LIMITS, ReportEvent, normalize_section_key
from app.schemas.candidate_event import CandidateEventFeed


class ReportSelector:
    def select(self, candidate_feed: CandidateEventFeed) -> dict[str, list[ReportEvent]]:
        grouped: dict[str, list[ReportEvent]] = defaultdict(list)

        for raw_section, events in candidate_feed.sections.items():
            normalized_section = normalize_section_key(raw_section)
            for event in events:
                grouped[normalized_section].append(
                    ReportEvent(
                        event_key=event.event_key,
                        title=event.title,
                        category=normalized_section,
                        sub_category=event.sub_category,
                        importance_score=event.importance_score,
                        heat_score=event.heat_score,
                        source_count=event.source_count,
                        source_links=list(event.source_links),
                        first_seen_at=event.first_seen_at,
                        last_seen_at=event.last_seen_at,
                    )
                )

        selected: dict[str, list[ReportEvent]] = {}
        for section_key, events in grouped.items():
            ordered = sorted(
                events,
                key=lambda item: (item.importance_score, item.heat_score, item.source_count),
                reverse=True,
            )
            selected[section_key] = ordered[: DETAIL_SECTION_LIMITS.get(section_key, len(ordered))]

        selected.setdefault("sector", [])
        selected.setdefault("policy", [])
        selected.setdefault("international", [])
        selected.setdefault("hot_topics", [])
        selected.setdefault("risk", [])
        selected["overview"] = self._build_overview(selected)
        return selected

    def build_full_report_projection(self, selected_sections: dict[str, list[ReportEvent]]) -> dict[str, list[ReportEvent]]:
        return {
            section_key: list(events[: FULL_REPORT_LIMITS.get(section_key, len(events))])
            for section_key, events in selected_sections.items()
        }

    def _build_overview(self, selected_sections: dict[str, list[ReportEvent]]) -> list[ReportEvent]:
        overview_candidates: list[ReportEvent] = []
        for section_key in ("sector", "policy", "international", "hot_topics", "risk"):
            overview_candidates.extend(selected_sections.get(section_key, []))

        ordered = sorted(
            overview_candidates,
            key=lambda item: (item.importance_score, item.heat_score, item.source_count),
            reverse=True,
        )

        deduped: list[ReportEvent] = []
        seen: set[str] = set()
        for item in ordered:
            marker = item.event_key or item.title
            if marker in seen:
                continue
            seen.add(marker)
            deduped.append(
                ReportEvent(
                    event_key=item.event_key,
                    title=item.title,
                    category="overview",
                    sub_category=item.sub_category,
                    importance_score=item.importance_score,
                    heat_score=item.heat_score,
                    source_count=item.source_count,
                    source_links=list(item.source_links),
                    first_seen_at=item.first_seen_at,
                    last_seen_at=item.last_seen_at,
                )
            )
            if len(deduped) >= FULL_REPORT_LIMITS["overview"]:
                break
        return deduped
