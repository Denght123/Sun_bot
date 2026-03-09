from __future__ import annotations

from app.collectors.base import CollectedItem
from app.parser_normalizer.normalize import normalize_collected_item
from app.rule_engine.classifier import classify_item



def build_item(title: str, summary: str, tag: str = ""):
    normalized = normalize_collected_item(
        CollectedItem(
            source_platform="baidu",
            source_type="hotsearch",
            title=title,
            summary=summary,
            external_id=title,
            collected_at="2026-03-07T07:20:00+08:00",
            raw_payload={"tag": tag},
        ),
        "Asia/Shanghai",
    )
    return classify_item(normalized)



def test_classifier_policy_priority_over_hot_topic() -> None:
    item = build_item("央行发布降准降息政策解读", "热搜持续发酵", tag="财经")

    assert item.category == "policy"



def test_classifier_identifies_sector_subcategory() -> None:
    item = build_item("AI服务器订单大增", "算力和半导体产业链活跃")

    assert item.category == "sector"
    assert item.sub_category == "ai"



def test_classifier_identifies_international_and_risk() -> None:
    international = build_item("美联储议息会议临近", "海外市场关注非农和通胀")
    risk = build_item("上市公司被立案调查", "存在退市风险提示")

    assert international.category == "international"
    assert risk.category == "risk"
