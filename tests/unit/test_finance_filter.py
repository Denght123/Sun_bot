from __future__ import annotations

from decimal import Decimal

from app.collectors.base import CollectedItem
from app.parser_normalizer.normalize import normalize_collected_item
from app.rule_engine.finance_filter import apply_finance_filter_to_item


def build_item(title: str, summary: str, tag: str, source_platform: str = "baidu"):
    normalized = normalize_collected_item(
        CollectedItem(
            source_platform=source_platform,
            source_type="hotsearch" if source_platform == "baidu" else "news",
            title=title,
            summary=summary,
            external_id=title,
            collected_at="2026-03-07T07:20:00+08:00",
            raw_payload={"tag": tag, "hot_score": 10000},
        ),
        "Asia/Shanghai",
    )
    return apply_finance_filter_to_item(normalized)



def test_finance_filter_keeps_finance_signal() -> None:
    item = build_item("央行回应降准降息节奏", "货币政策和流动性受到市场关注", "财经")

    assert item.is_finance_related is True
    assert item.process_status == "processed"
    assert item.finance_score is not None
    assert item.finance_score >= Decimal("3.00")



def test_finance_filter_rejects_entertainment_signal() -> None:
    item = build_item("某综艺总决赛", "明星和粉丝热议", "娱乐")

    assert item.is_finance_related is False
    assert item.process_status == "filtered"



def test_finance_filter_gives_cls_higher_base_score() -> None:
    item = build_item("基金公司披露新发产品", "基金和理财产品发行升温", "", source_platform="cls")

    assert item.is_finance_related is True
    assert item.finance_score is not None
    assert item.finance_score >= Decimal("4.00")
