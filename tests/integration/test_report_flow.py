from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.main as main_module
import app.services.scheduler_dispatch_flow as scheduler_flow_module
from app.collectors.base import CollectedItem
from app.core.config import get_settings
from app.core.time import now_in_timezone
from app.db.base import Base
from app.db.model_definitions import ReportSection
from app.db.session import get_db
from app.main import create_app
from app.reports.llm_overlay import LLMSectionCandidate
from app.schemas.candidate_event import CandidateEvent, CandidateEventFeed
from app.services.collection_pipeline import CollectionPipeline
from app.services.report_service import ReportGeneratorService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
API_PREFIX = get_settings().api_prefix


class FixtureCollector:
    def __init__(self, source_platform: str, items: list[CollectedItem]) -> None:
        self.source_platform = source_platform
        self._items = items

    def collect(self) -> list[CollectedItem]:
        return self._items


class StubRedis:
    def ping(self) -> bool:
        return True

    def close(self) -> None:
        return None


class FakeLLMClient:
    def __init__(self, candidates: list[LLMSectionCandidate] | None = None, error: Exception | None = None) -> None:
        self.candidates = candidates or []
        self.error = error

    def summarize_sections(self, *, report_date: str, section_payloads: dict[str, list[dict[str, object]]]) -> list[LLMSectionCandidate]:
        if self.error is not None:
            raise self.error
        return self.candidates


@pytest.fixture(autouse=True)
def stub_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    stub = StubRedis()
    monkeypatch.setattr(main_module, "get_redis_client", lambda: stub)
    monkeypatch.setattr(main_module, "close_redis_client", lambda: None)


@pytest.fixture
def settings():
    return get_settings().model_copy(update={"candidate_event_limit_per_section": 10})


@pytest.fixture
def sqlite_engine():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def app(sqlite_engine):
    application = create_app()

    def override_get_db():
        with Session(sqlite_engine) as session:
            yield session

    application.dependency_overrides[get_db] = override_get_db
    try:
        yield application
    finally:
        application.dependency_overrides.clear()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def fixture_collectors() -> list[FixtureCollector]:
    batch = json.loads((FIXTURES / "pipeline" / "mixed_batch.json").read_text(encoding="utf-8"))
    items = [CollectedItem(**row) for row in batch]
    grouped: dict[str, list[CollectedItem]] = {}
    for item in items:
        grouped.setdefault(item.source_platform, []).append(item)
    return [FixtureCollector(source_platform=source, items=source_items) for source, source_items in grouped.items()]


def seed_report_source_data(session: Session, fixture_collectors: list[FixtureCollector], settings) -> None:
    pipeline = CollectionPipeline(session=session, settings=settings, collectors=fixture_collectors)
    pipeline.run(report_date=date(2026, 3, 7))


def build_sparse_feed(report_date: date) -> CandidateEventFeed:
    now = now_in_timezone()
    return CandidateEventFeed(
        report_date=report_date,
        window_start=now,
        window_end=now,
        sections={
            "overview": [],
            "sector": [
                CandidateEvent(
                    event_key="sector-1",
                    title="半导体板块成交活跃",
                    category="sector",
                    importance_score="9.0",
                    heat_score="8.0",
                    source_count=3,
                    source_links=["https://example.com/sector-1"],
                )
            ],
            "policy": [
                CandidateEvent(
                    event_key="policy-1",
                    title="监管披露新阶段性安排",
                    category="policy",
                    importance_score="8.6",
                    heat_score="7.2",
                    source_count=2,
                    source_links=["https://example.com/policy-1"],
                )
            ],
            "international": [
                CandidateEvent(
                    event_key="intl-1",
                    title="海外市场波动扩大",
                    category="international",
                    importance_score="8.2",
                    heat_score="7.6",
                    source_count=2,
                    source_links=["https://example.com/intl-1"],
                )
            ],
            "risk": [
                CandidateEvent(
                    event_key="risk-1",
                    title="个别产品净值波动加大",
                    category="risk",
                    importance_score="7.9",
                    heat_score="6.8",
                    source_count=2,
                    source_links=["https://example.com/risk-1"],
                )
            ],
            "hot_topic": [
                CandidateEvent(
                    event_key="hot-1",
                    title="热搜聚焦黄金资产",
                    category="hot_topic",
                    importance_score="7.5",
                    heat_score="8.8",
                    source_count=4,
                    source_links=["https://example.com/hot-1"],
                )
            ],
        },
    )


def test_report_service_generates_sections_and_chunks(sqlite_engine, fixture_collectors, settings) -> None:
    with Session(sqlite_engine) as session:
        seed_report_source_data(session, fixture_collectors, settings)
        service = ReportGeneratorService(session=session, settings=settings)

        result = service.generate(date(2026, 3, 7))
        report = result.report

        assert report.generation_status == "success"
        assert report.fallback_used is False
        assert report.full_text
        assert report.total_word_count == len(report.full_text)
        assert 1 <= report.total_message_chunks <= 6
        assert isinstance(report.link_bundle, dict)
        assert report.link_bundle["message_chunks"]
        assert "【免责声明】" in report.full_text

        sections = session.query(ReportSection).order_by(ReportSection.sort_order).all()
        section_keys = [section.section_key for section in sections]
        assert section_keys == ["overview", "sector", "policy", "international", "hot_topics", "risk", "help"]
        assert all(section.message_chunks for section in sections)


def test_keyword_content_menu_returns_full_report_and_section(client, sqlite_engine, fixture_collectors, settings) -> None:
    with Session(sqlite_engine) as session:
        seed_report_source_data(session, fixture_collectors, settings)
        service = ReportGeneratorService(session=session, settings=settings)
        service.generate(date(2026, 3, 7))
        session.commit()

    full_response = client.get(
        f"{API_PREFIX}/content/menu",
        headers={"Authorization": f"Bearer {settings.sender_token}"},
        params={"report_date": "2026-03-07", "keyword": "早报"},
    )
    assert full_response.status_code == 200
    full_data = full_response.json()["data"]
    assert full_data["title"] == "完整精简版日报"
    assert full_data["message_chunks"]

    section_response = client.get(
        f"{API_PREFIX}/content/menu",
        headers={"Authorization": f"Bearer {settings.sender_token}"},
        params={"report_date": "2026-03-07", "keyword": "板块"},
    )
    assert section_response.status_code == 200
    section_data = section_response.json()["data"]
    assert section_data["title"] == "板块观察"
    assert section_data["message_chunks"]


def test_admin_report_detail_returns_sections_and_totals(client, sqlite_engine, fixture_collectors, settings, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_collection_pipeline(*, session: Session, report_date: date | None = None):
        pipeline = CollectionPipeline(session=session, settings=settings, collectors=fixture_collectors)
        return pipeline.run(report_date=report_date)

    monkeypatch.setattr(scheduler_flow_module, "run_collection_pipeline", fake_run_collection_pipeline)

    run_response = client.post(
        f"{API_PREFIX}/admin/report/run",
        headers={"Authorization": f"Bearer {settings.admin_token}"},
        json={"report_date": "2026-03-07"},
    )
    assert run_response.status_code == 200

    detail_response = client.get(
        f"{API_PREFIX}/admin/reports/2026-03-07",
        headers={"Authorization": f"Bearer {settings.admin_token}"},
    )
    assert detail_response.status_code == 200
    data = detail_response.json()["data"]
    assert data["total_word_count"] > 0
    assert 1 <= data["total_message_chunks"] <= 6
    assert data["link_bundle"]["message_chunks"]
    assert [section["section_key"] for section in data["sections"]] == [
        "overview",
        "sector",
        "policy",
        "international",
        "hot_topics",
        "risk",
        "help",
    ]


def test_llm_invalid_and_missing_sections_fall_back_to_template(sqlite_engine, settings, monkeypatch: pytest.MonkeyPatch) -> None:
    report_date = date(2026, 3, 7)
    feed = build_sparse_feed(report_date)

    with Session(sqlite_engine) as session:
        service = ReportGeneratorService(
            session=session,
            settings=settings.model_copy(update={"llm_enabled": True}),
            llm_client=FakeLLMClient(
                candidates=[
                    LLMSectionCandidate(
                        section_key="sector",
                        content="【板块观察】\n1. 事实：半导体板块成交活跃。影响：相关板块短期关注度上升，仍需结合公开信息观察。",
                        event_keys=["sector-1"],
                    ),
                    LLMSectionCandidate(
                        section_key="policy",
                        content="【政策动态】\n1. 建议买入政策受益方向。",
                        event_keys=["policy-1"],
                    ),
                ]
            ),
        )
        monkeypatch.setattr(service.repository, "load_candidate_feed", lambda **_: feed)

        result = service.generate(report_date)

        assert result.report.generation_status == "success"
        assert result.report.fallback_used is True
        assert any(warning == "invalid_section:policy" for warning in result.warnings)
        assert any(warning == "missing_section:international" for warning in result.warnings)
        assert result.report.link_bundle["sections"]["sector"]["render_mode"] == "hybrid"

        stored_sections = {
            section.section_key: section
            for section in session.query(ReportSection).all()
        }
        assert "建议买入" not in stored_sections["policy"].content
        assert stored_sections["sector"].content.startswith("【板块观察】\n1. 事实：半导体板块成交活跃")


def test_llm_error_produces_fallback_success(sqlite_engine, settings, monkeypatch: pytest.MonkeyPatch) -> None:
    report_date = date(2026, 3, 7)
    feed = build_sparse_feed(report_date)

    with Session(sqlite_engine) as session:
        service = ReportGeneratorService(
            session=session,
            settings=settings.model_copy(update={"llm_enabled": True}),
            llm_client=FakeLLMClient(error=RuntimeError("timeout")),
        )
        monkeypatch.setattr(service.repository, "load_candidate_feed", lambda **_: feed)

        result = service.generate(report_date)

        assert result.report.generation_status == "fallback_success"
        assert result.report.fallback_used is True
        assert any(warning.startswith("llm_error:") for warning in result.warnings)
        stored_sections = session.query(ReportSection).all()
        assert all(section.content for section in stored_sections)


def test_report_composer_keeps_sparse_input_within_chunk_limit(sqlite_engine, settings, monkeypatch: pytest.MonkeyPatch) -> None:
    report_date = date(2026, 3, 7)
    feed = build_sparse_feed(report_date)

    with Session(sqlite_engine) as session:
        service = ReportGeneratorService(session=session, settings=settings)
        monkeypatch.setattr(service.repository, "load_candidate_feed", lambda **_: feed)

        result = service.generate(report_date)

        assert result.report.total_message_chunks <= 6
        assert result.report.total_word_count > 0
        assert "【原文链接集合】" in result.report.full_text
