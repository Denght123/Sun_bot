from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from app.parser_normalizer.schemas import NormalizedRawItem

POSITIVE_KEYWORDS = {
    "财经",
    "金融",
    "基金",
    "理财",
    "股票",
    "a股",
    "港股",
    "美股",
    "债券",
    "黄金",
    "原油",
    "汇率",
    "人民币",
    "美元",
    "ipo",
    "并购",
    "业绩",
    "利润",
    "营收",
    "财报",
    "央行",
    "降准",
    "降息",
    "监管",
    "政策",
    "证券",
    "券商",
    "保险",
    "银行",
    "地产",
    "新能源",
    "医药",
    "消费",
    "ai",
    "半导体",
    "产业链",
    "资本市场",
    "非农",
}

NEGATIVE_KEYWORDS = {
    "明星",
    "综艺",
    "电视剧",
    "电影",
    "演唱会",
    "恋情",
    "婚礼",
    "粉丝",
    "饭圈",
    "选秀",
    "娱乐圈",
    "艺人",
    "男团",
    "女团",
    "电竞",
    "直播翻车",
    "网红",
}

SOURCE_BASE_SCORES = {
    "cls": Decimal("4.00"),
    "baidu": Decimal("0.80"),
}


def apply_finance_filter(items: list[NormalizedRawItem]) -> list[NormalizedRawItem]:
    return [apply_finance_filter_to_item(item) for item in items]


def apply_finance_filter_to_item(item: NormalizedRawItem) -> NormalizedRawItem:
    text = build_text(item)
    positive_hits = sum(1 for keyword in POSITIVE_KEYWORDS if keyword in text)
    negative_hits = sum(1 for keyword in NEGATIVE_KEYWORDS if keyword in text)
    score = SOURCE_BASE_SCORES.get(item.source_platform, Decimal("1.00"))
    score += Decimal("1.20") * positive_hits
    score -= Decimal("2.40") * negative_hits

    tag = str(item.raw_payload.get("tag", "")).lower()
    if any(keyword in tag for keyword in ("财经", "finance", "股", "基金", "经济")):
        score += Decimal("1.50")
    if any(keyword in tag for keyword in ("娱乐", "明星", "综艺")):
        score -= Decimal("2.50")

    is_finance_related = score >= Decimal("3.00") and not (negative_hits > positive_hits and item.source_platform != "cls")
    quantized_score = score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return item.model_copy(
        update={
            "is_finance_related": is_finance_related,
            "finance_score": quantized_score,
            "process_status": "processed" if is_finance_related else "filtered",
        }
    )


def build_text(item: NormalizedRawItem) -> str:
    title = item.title.lower()
    summary = (item.summary or "").lower()
    payload_bits = [str(item.raw_payload.get("tag", "")), str(item.raw_payload.get("topic", "")), str(item.raw_payload.get("label_name", ""))]
    payload_text = " ".join(payload_bits).lower()
    return f"{title} {summary} {payload_text}"
