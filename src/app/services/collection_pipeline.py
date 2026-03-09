from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from sqlalchemy.orm import Session

from app.collectors.base import BaseCollector
from app.core.config import Settings, get_settings
from app.core.time_window import build_report_window, default_report_date, is_in_window
from app.db.repositories import EventClusterRepository, RawItemRepository
from app.finance_collectors import CLSCollector
from app.parser_normalizer import normalize_collected_items, normalized_item_from_model
from app.rule_engine import apply_finance_filter, classify_item, cluster_items, deduplicate_items
from app.schemas.candidate_event import PipelineRunResult
from app.services.candidate_event_feed import build_candidate_event_feed
from app.social_collectors import BaiduHotsearchCollector


class CollectionPipeline:
    def __init__(self, session: Session, settings: Settings | None = None, collectors: Sequence[BaseCollector] | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.raw_items = RawItemRepository(session)
        self.event_clusters = EventClusterRepository(session)
        self.collectors = list(collectors) if collectors is not None else [
            CLSCollector(settings=self.settings),
            BaiduHotsearchCollector(settings=self.settings),
        ]

    def run(self, report_date: date | None = None) -> PipelineRunResult:
        target_date = report_date or default_report_date(self.settings.timezone)
        window = build_report_window(target_date, self.settings.timezone)
        warnings: list[str] = []

        collected_items = []
        sources: list[str] = []
        for collector in self.collectors:
            sources.append(collector.source_platform)
            try:
                collected_items.extend(collector.collect())
            except Exception as exc:
                warnings.append(f"{collector.source_platform}: {exc}")

        normalized_items = deduplicate_items(normalize_collected_items(collected_items, self.settings.timezone))
        persisted_items, inserted_count = self._upsert_raw_items(normalized_items)
        in_window_items = [item for item in persisted_items if is_in_window(item.published_at or item.collected_at, window)]
        filtered_items = apply_finance_filter(in_window_items)
        self._update_raw_item_processing(filtered_items)
        classified_items = [classify_item(item) for item in filtered_items if item.is_finance_related]

        self._clear_clusters(target_date)
        clusters = cluster_items(classified_items, target_date)
        self._persist_clusters(clusters)
        candidate_feed = build_candidate_event_feed(
            report_date=target_date,
            window_start=window.start,
            window_end=window.end,
            clusters=clusters,
            limit_per_section=self.settings.candidate_event_limit_per_section,
        )
        self.session.commit()

        return PipelineRunResult(
            report_date=target_date,
            window_start=window.start,
            window_end=window.end,
            sources=sources,
            collected_count=len(collected_items),
            inserted_count=inserted_count,
            window_item_count=len(in_window_items),
            finance_item_count=len(classified_items),
            cluster_count=len(clusters),
            warnings=warnings,
            candidate_feed=candidate_feed,
        )

    def _upsert_raw_items(self, items):
        persisted = []
        inserted_count = 0
        for item in items:
            model, created = self.raw_items.upsert(item)
            if created:
                inserted_count += 1
            persisted.append(normalized_item_from_model(model))
        return persisted, inserted_count

    def _find_existing_raw_item(self, item):
        return self.raw_items.find_existing(item)

    def _update_raw_item_processing(self, items) -> None:
        for item in items:
            if item.raw_item_id is None:
                continue
            self.raw_items.update_processing(
                raw_item_id=item.raw_item_id,
                is_finance_related=item.is_finance_related,
                finance_score=item.finance_score,
                process_status=item.process_status,
            )

    def _clear_clusters(self, report_date: date) -> None:
        self.event_clusters.clear_for_date(report_date)

    def _persist_clusters(self, clusters) -> None:
        for cluster in clusters:
            cluster_model = self.event_clusters.create(cluster)
            for item in cluster.items:
                if item.raw_item_id is None:
                    continue
                self.event_clusters.add_source(
                    cluster_id=cluster_model.id,
                    raw_item_id=item.raw_item_id,
                    source_weight=item.source_weight,
                )


def run_collection_pipeline(session: Session, report_date: date | None = None) -> PipelineRunResult:
    return CollectionPipeline(session=session).run(report_date=report_date)
