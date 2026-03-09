from __future__ import annotations

from hashlib import sha256
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from dateutil import parser

from app.collectors.base import CollectedItem
from app.db.model_definitions import RawItem
from app.parser_normalizer.schemas import ClassifiedItem, NormalizedRawItem

TRACKING_QUERY_KEYS = {
    "from",
    "feature",
    "fr",
    "oq",
    "rsv_idx",
    "rsv_dl",
    "rsv_t",
    "sa",
    "spm",
}
SOURCE_WEIGHTS = {
    "cls": Decimal("3.50"),
    "baidu": Decimal("1.20"),
}
WRAPPER_PAIRS = (("【", "】"), ("[", "]"), ("（", "）"), ("(", ")"), ("#", "#"))
WHITESPACE_RE = re.compile(r"\s+")
NON_WORD_RE = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff]+")


def normalize_collected_item(item: CollectedItem, timezone_name: str) -> NormalizedRawItem:
    title = normalize_title(item.title)
    summary = normalize_summary(item.summary)
    url = canonicalize_url(item.url)
    fallback_url = canonicalize_url(item.fallback_url)
    published_at = normalize_datetime(item.published_at, timezone_name)
    collected_at = normalize_datetime(item.collected_at, timezone_name) or datetime.now(ZoneInfo(timezone_name))
    raw_payload = dict(item.raw_payload)
    raw_payload.setdefault("canonical_url", url)
    raw_payload.setdefault("source_platform", item.source_platform)
    raw_payload.setdefault("source_type", item.source_type)
    source_weight = SOURCE_WEIGHTS.get(item.source_platform, Decimal("1.00"))
    heat_score = extract_heat_score(raw_payload)
    raw_payload.setdefault("source_weight", str(source_weight))
    raw_payload.setdefault("heat_score", str(heat_score))
    content_hash = build_content_hash(title=title, summary=summary, canonical_url=url, published_at=published_at)
    return NormalizedRawItem(
        source_platform=item.source_platform,
        source_type=item.source_type,
        external_id=normalize_optional_text(item.external_id),
        title=title,
        summary=summary,
        url=url,
        fallback_url=fallback_url,
        published_at=published_at,
        collected_at=collected_at,
        content_hash=content_hash,
        raw_payload=raw_payload,
        language=item.language or "zh-CN",
        source_weight=source_weight,
        heat_score=heat_score,
        canonical_url=url,
    )


def normalize_collected_items(items: list[CollectedItem], timezone_name: str) -> list[NormalizedRawItem]:
    return [normalize_collected_item(item, timezone_name) for item in items if normalize_optional_text(item.title)]


def normalized_item_from_model(raw_item: RawItem) -> NormalizedRawItem:
    raw_payload = dict(raw_item.raw_payload or {})
    return NormalizedRawItem(
        raw_item_id=raw_item.id,
        source_platform=raw_item.source_platform,
        source_type=raw_item.source_type,
        external_id=raw_item.external_id,
        title=raw_item.title,
        summary=raw_item.summary,
        url=raw_item.url,
        fallback_url=raw_item.fallback_url,
        published_at=raw_item.published_at,
        collected_at=raw_item.collected_at,
        content_hash=raw_item.content_hash,
        raw_payload=raw_payload,
        language=raw_item.language,
        is_finance_related=raw_item.is_finance_related,
        finance_score=raw_item.finance_score,
        process_status=raw_item.process_status,
        source_weight=extract_decimal(raw_payload.get("source_weight")) or SOURCE_WEIGHTS.get(raw_item.source_platform, Decimal("1.00")),
        heat_score=extract_heat_score(raw_payload),
        canonical_url=raw_payload.get("canonical_url") or raw_item.url,
    )


def to_classified_item(item: NormalizedRawItem, category: str, sub_category: str | None = None) -> ClassifiedItem:
    return ClassifiedItem(**item.model_dump(), category=category, sub_category=sub_category)


def normalize_title(value: str) -> str:
    text = normalize_optional_text(value) or ""
    previous = None
    while text and text != previous:
        previous = text
        for left, right in WRAPPER_PAIRS:
            if text.startswith(left) and text.endswith(right):
                candidate = text[len(left) : len(text) - len(right)].strip()
                if candidate:
                    text = candidate
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_summary(value: str | None) -> str | None:
    text = normalize_optional_text(value)
    if not text:
        return None
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).replace("\u3000", " ").strip()
    return text or None


def normalize_datetime(value: datetime | str | int | float | None, timezone_name: str) -> datetime | None:
    if value is None:
        return None
    timezone = ZoneInfo(timezone_name)
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        dt = _from_timestamp(float(value), timezone)
    else:
        text = str(value).strip()
        if re.fullmatch(r"\d{10,13}", text):
            dt = _from_timestamp(float(text), timezone)
        else:
            dt = parser.parse(text)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone)
    return dt.astimezone(timezone)


def _from_timestamp(timestamp: float, timezone: ZoneInfo) -> datetime:
    if timestamp > 10_000_000_000:
        timestamp /= 1000
    return datetime.fromtimestamp(timestamp, tz=timezone)


def canonicalize_url(value: str | None) -> str | None:
    text = normalize_optional_text(value)
    if not text:
        return None
    parsed = urlparse(text)
    if not parsed.scheme or not parsed.netloc:
        return text
    filtered_query = [(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True) if not key.lower().startswith("utm_") and key.lower() not in TRACKING_QUERY_KEYS]
    normalized = parsed._replace(fragment="", query=urlencode(filtered_query, doseq=True))
    return urlunparse(normalized)


def build_content_hash(*, title: str, summary: str | None, canonical_url: str | None, published_at: datetime | None) -> str:
    published_key = published_at.isoformat() if published_at else ""
    parts = [normalize_hash_text(title), normalize_hash_text(summary or ""), canonical_url or "", published_key]
    return sha256("|".join(parts).encode("utf-8")).hexdigest()


def normalize_hash_text(value: str) -> str:
    return NON_WORD_RE.sub(" ", value).strip().lower()


def extract_heat_score(raw_payload: dict[str, object]) -> Decimal:
    keys = (
        "heat_score",
        "hot_score",
        "hot",
        "hotIndex",
        "hot_index",
        "displayHotScore",
        "heat",
    )
    for key in keys:
        if key in raw_payload:
            decimal_value = extract_decimal(raw_payload.get(key))
            if decimal_value is not None:
                return decimal_value
    return Decimal("0")


def extract_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    text = normalize_optional_text(value)
    if not text:
        return None
    multiplier = Decimal("1")
    if text.endswith("万"):
        multiplier = Decimal("10000")
        text = text[:-1]
    elif text.endswith("亿"):
        multiplier = Decimal("100000000")
        text = text[:-1]
    text = text.replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return Decimal(match.group(0)) * multiplier
    except InvalidOperation:
        return None
