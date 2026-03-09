from __future__ import annotations

import json
from pathlib import Path
from zoneinfo import ZoneInfo

from app.collectors.base import CollectedItem
from app.finance_collectors.cls_collector import CLSCollector
from app.parser_normalizer.normalize import normalize_collected_item
from app.social_collectors.baidu_hotsearch_collector import BaiduHotsearchCollector

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SHANGHAI = ZoneInfo("Asia/Shanghai")


def test_cls_collector_parse_html() -> None:
    html = (FIXTURES / "cls" / "sample_list.html").read_text(encoding="utf-8")
    collector = CLSCollector()

    items = collector.parse_html(html)

    assert len(items) == 3
    assert items[0].source_platform == "cls"
    assert items[0].external_id == "1001"
    assert items[0].title == "央行：继续实施适度宽松的货币政策"


def test_baidu_collector_parse_html() -> None:
    html = (FIXTURES / "baidu" / "sample_hotsearch.html").read_text(encoding="utf-8")
    collector = BaiduHotsearchCollector()

    items = collector.parse_html(html)

    assert len(items) == 3
    assert items[0].source_platform == "baidu"
    assert items[0].raw_payload["hot_score"] == 9823456
    assert items[2].raw_payload["tag"] == "娱乐"


def test_normalize_collected_item_generates_stable_shape() -> None:
    item = CollectedItem(
        source_platform="baidu",
        source_type="hotsearch",
        external_id="央行回应降准降息节奏",
        title="【央行回应降准降息节奏】",
        summary="货币政策工具和流动性安排受到市场关注。",
        url="https://www.baidu.com/s?wd=test&utm_source=feed",
        fallback_url="https://www.baidu.com/s?wd=test&utm_source=feed",
        collected_at="2026-03-07T07:20:00+08:00",
        raw_payload={"tag": "财经", "hot_score": 9823456},
    )

    normalized = normalize_collected_item(item, "Asia/Shanghai")

    assert normalized.title == "央行回应降准降息节奏"
    assert normalized.url == "https://www.baidu.com/s?wd=test"
    assert normalized.source_weight > 0
    assert normalized.heat_score > 0
    assert normalized.collected_at.tzinfo == SHANGHAI
    assert len(normalized.content_hash) == 64


def test_normalize_fixture_batch() -> None:
    batch = json.loads((FIXTURES / "pipeline" / "mixed_batch.json").read_text(encoding="utf-8"))

    normalized = [normalize_collected_item(CollectedItem(**row), "Asia/Shanghai") for row in batch]

    assert len(normalized) == 4
    assert normalized[0].published_at is not None
    assert normalized[1].raw_payload["tag"] == "财经"
    assert normalized[0].collected_at.tzinfo == SHANGHAI
