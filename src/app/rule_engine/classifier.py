from __future__ import annotations

from app.parser_normalizer.normalize import to_classified_item
from app.parser_normalizer.schemas import ClassifiedItem, NormalizedRawItem
from app.rule_engine.taxonomy import (
    HOT_TOPIC_KEYWORDS,
    INTERNATIONAL_KEYWORDS,
    POLICY_KEYWORDS,
    RISK_KEYWORDS,
    SECTOR_KEYWORDS,
)


def classify_item(item: NormalizedRawItem) -> ClassifiedItem:
    text = build_text(item)
    sub_category = detect_sub_category(text)

    if contains_keyword(text, RISK_KEYWORDS):
        category = "risk"
    elif contains_keyword(text, POLICY_KEYWORDS):
        category = "policy"
    elif contains_keyword(text, INTERNATIONAL_KEYWORDS):
        category = "international"
    elif sub_category is not None:
        category = "sector"
    elif item.source_type == "hotsearch" or contains_keyword(text, HOT_TOPIC_KEYWORDS):
        category = "hot_topic"
    else:
        category = "overview"

    return to_classified_item(item, category=category, sub_category=sub_category)


def detect_sub_category(text: str) -> str | None:
    for sub_category, keywords in SECTOR_KEYWORDS.items():
        if contains_keyword(text, keywords):
            return sub_category
    return None


def contains_keyword(text: str, keywords: set[str]) -> bool:
    return any(keyword.lower() in text for keyword in keywords)


def build_text(item: NormalizedRawItem) -> str:
    payload_text = " ".join(
        str(item.raw_payload.get(key, "")) for key in ("tag", "topic", "label_name", "category")
    )
    return f"{item.title} {item.summary or ''} {payload_text}".lower()
