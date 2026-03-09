from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.collectors.base import CollectedItem
from app.parser_normalizer.normalize import normalize_collected_item
from app.rule_engine.classifier import classify_item
from app.rule_engine.clusterer import cluster_items



def build_item(source_platform: str, title: str, summary: str, url: str, hot_score: int = 0):
    normalized = normalize_collected_item(
        CollectedItem(
            source_platform=source_platform,
            source_type="news" if source_platform == "cls" else "hotsearch",
            title=title,
            summary=summary,
            url=url,
            fallback_url=url,
            external_id=title,
            published_at="2026-03-07T07:00:00+08:00",
            collected_at="2026-03-07T07:20:00+08:00",
            raw_payload={"hot_score": hot_score, "tag": "财经"},
        ),
        "Asia/Shanghai",
    )
    normalized = normalized.model_copy(update={"is_finance_related": True, "finance_score": Decimal("5.00")})
    return classify_item(normalized)



def test_clusterer_merges_same_event_across_sources() -> None:
    items = [
        build_item("cls", "央行继续实施适度宽松货币政策", "支持资本市场稳定发展", "https://www.cls.cn/detail/1001"),
        build_item("baidu", "央行继续实施适度宽松货币政策", "市场高度关注降准降息节奏", "https://www.baidu.com/s?wd=央行继续实施适度宽松货币政策", hot_score=9000000),
    ]

    clusters = cluster_items(items, date(2026, 3, 7))

    assert len(clusters) == 1
    assert clusters[0].source_count == 2
    assert clusters[0].title == "央行继续实施适度宽松货币政策"



def test_clusterer_keeps_distinct_events_separate() -> None:
    items = [
        build_item("cls", "央行继续实施适度宽松货币政策", "支持资本市场稳定发展", "https://www.cls.cn/detail/1001"),
        build_item("baidu", "某综艺总决赛", "娱乐话题热搜", "https://www.baidu.com/s?wd=某综艺总决赛", hot_score=9000000),
    ]

    clusters = cluster_items(items, date(2026, 3, 7))

    assert len(clusters) == 2
