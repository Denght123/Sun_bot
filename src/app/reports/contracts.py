from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

REPORT_DISCLAIMER = "本项目仅用于信息整理与消息推送，不构成任何投资建议。投资决策请独立判断。"
HELP_TITLE = "功能菜单"
HELP_CONTENT = "可回复：功能 / 早报 / 板块 / 政策 / 国际 / 热搜 / 风险 / 帮助"

SECTION_ALIAS_MAP: dict[str, str] = {
    "overview": "overview",
    "sector": "sector",
    "policy": "policy",
    "international": "international",
    "risk": "risk",
    "hot_topic": "hot_topics",
    "hot_topics": "hot_topics",
}
SECTION_TITLE_MAP: dict[str, str] = {
    "overview": "今日总览",
    "sector": "板块观察",
    "policy": "政策动态",
    "international": "国际事件",
    "hot_topics": "热点追踪",
    "risk": "风险提示",
}
FULL_REPORT_SECTION_ORDER = ("overview", "sector", "policy", "international", "risk")
DETAIL_SECTION_ORDER = ("overview", "sector", "policy", "international", "hot_topics", "risk")
KEYWORD_SECTION_MAP: dict[str, str] = {
    "板块": "sector",
    "政策": "policy",
    "国际": "international",
    "热搜": "hot_topics",
    "风险": "risk",
}
DETAIL_SECTION_LIMITS: dict[str, int] = {
    "overview": 5,
    "sector": 10,
    "policy": 10,
    "international": 10,
    "hot_topics": 10,
    "risk": 3,
}
FULL_REPORT_LIMITS: dict[str, int] = {
    "overview": 5,
    "sector": 4,
    "policy": 4,
    "international": 3,
    "risk": 3,
}
FULL_REPORT_BLOCK_LIMITS: dict[str, int] = {
    "overview": 320,
    "sector": 340,
    "policy": 340,
    "international": 280,
    "risk": 220,
}
TARGET_MIN_CHARS = 1200
TARGET_MAX_CHARS = 1800
MAX_DAILY_MESSAGE_CHUNKS = 6
SECTION_CHUNK_MAX_CHARS = 420
MAX_LINKS_IN_FULL_REPORT = 5
BANNED_ADVICE_PHRASES = (
    "投资建议",
    "建议买入",
    "建议卖出",
    "建议加仓",
    "建议减仓",
    "抄底",
    "止盈",
    "止损",
    "建仓",
    "仓位",
)


@dataclass(slots=True)
class ReportEvent:
    event_key: str
    title: str
    category: str
    sub_category: str | None
    importance_score: Decimal
    heat_score: Decimal
    source_count: int
    source_links: list[str] = field(default_factory=list)
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None


@dataclass(slots=True)
class SectionDraft:
    section_key: str
    title: str
    events: list[ReportEvent]
    content: str
    brief_block: str
    message_chunks: list[str]
    render_mode: str = "template"


@dataclass(slots=True)
class GeneratedReportBundle:
    report_date: date
    full_text: str
    message_chunks: list[str]
    total_word_count: int
    total_message_chunks: int
    link_bundle: dict[str, object]
    sections: list[SectionDraft]
    generation_status: str
    fallback_used: bool
    warnings: list[str] = field(default_factory=list)


def normalize_section_key(section_key: str) -> str:
    return SECTION_ALIAS_MAP.get(section_key, section_key)


def contains_investment_advice(text: str) -> bool:
    return any(phrase in text for phrase in BANNED_ADVICE_PHRASES)
