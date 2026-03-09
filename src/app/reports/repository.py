from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.db.model_definitions import DailyReport, EventCluster, EventSource, RawItem, ReportSection
from app.reports.contracts import DETAIL_SECTION_ORDER, SectionDraft
from app.schemas.candidate_event import CandidateEvent, CandidateEventFeed


class ReportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_report(self, report_date: date) -> DailyReport | None:
        return self.session.scalar(
            select(DailyReport)
            .options(selectinload(DailyReport.sections))
            .where(DailyReport.report_date == report_date)
        )

    def load_candidate_feed(self, *, report_date: date, window_start: datetime, window_end: datetime) -> CandidateEventFeed:
        rows = self.session.execute(
            select(EventCluster, EventSource, RawItem)
            .join(EventSource, EventSource.cluster_id == EventCluster.id)
            .join(RawItem, RawItem.id == EventSource.raw_item_id)
            .where(EventCluster.cluster_date == report_date)
            .order_by(EventCluster.importance_score.desc(), EventCluster.heat_score.desc(), EventCluster.source_count.desc())
        ).all()

        cluster_map: dict[int, CandidateEvent] = {}
        cluster_category_map: dict[int, str] = {}
        seen_links_by_cluster: dict[int, set[str]] = {}
        for cluster, _source, raw_item in rows:
            cluster_id = int(cluster.id)
            if cluster_id not in cluster_map:
                cluster_map[cluster_id] = CandidateEvent(
                    event_key=cluster.event_key,
                    title=cluster.title,
                    category=cluster.category,
                    sub_category=cluster.sub_category,
                    importance_score=cluster.importance_score,
                    heat_score=cluster.heat_score,
                    source_count=cluster.source_count,
                    source_links=[],
                    raw_item_ids=[],
                    first_seen_at=cluster.first_seen_at,
                    last_seen_at=cluster.last_seen_at,
                )
                cluster_category_map[cluster_id] = cluster.category
                seen_links_by_cluster[cluster_id] = set()
            event = cluster_map[cluster_id]
            if raw_item.id is not None and int(raw_item.id) not in event.raw_item_ids:
                event.raw_item_ids.append(int(raw_item.id))
            for candidate in (raw_item.url, raw_item.fallback_url):
                if candidate and candidate not in seen_links_by_cluster[cluster_id]:
                    seen_links_by_cluster[cluster_id].add(candidate)
                    event.source_links.append(candidate)

        sections: dict[str, list[CandidateEvent]] = {
            "overview": [],
            "sector": [],
            "policy": [],
            "international": [],
            "risk": [],
            "hot_topic": [],
        }
        for cluster_id, event in cluster_map.items():
            sections.setdefault(cluster_category_map[cluster_id], []).append(event)

        return CandidateEventFeed(
            report_date=report_date,
            window_start=window_start,
            window_end=window_end,
            sections=sections,
        )

    def replace_sections(self, *, report: DailyReport, sections: list[SectionDraft]) -> None:
        self.session.execute(delete(ReportSection).where(ReportSection.report_id == report.id))
        self.session.flush()
        for sort_order, section in enumerate(sections, start=1):
            self.session.add(
                ReportSection(
                    report_id=report.id,
                    section_key=section.section_key,
                    title=section.title,
                    content=section.content,
                    message_chunks=section.message_chunks,
                    sort_order=sort_order,
                )
            )
        self.session.flush()

    def get_section_by_key(self, *, report_date: date, section_key: str) -> ReportSection | None:
        return self.session.scalar(
            select(ReportSection)
            .join(DailyReport, DailyReport.id == ReportSection.report_id)
            .where(DailyReport.report_date == report_date, ReportSection.section_key == section_key)
        )

    def list_sections(self, *, report_id: int) -> list[ReportSection]:
        return self.session.scalars(
            select(ReportSection)
            .where(ReportSection.report_id == report_id)
            .order_by(ReportSection.sort_order, ReportSection.id)
        ).all()

    def build_default_sections(self) -> list[str]:
        return list(DETAIL_SECTION_ORDER)
