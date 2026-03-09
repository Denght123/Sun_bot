from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote

from bs4 import BeautifulSoup

from app.collectors.base import BaseCollector, CollectedItem

NEXT_DATA_PATTERN = re.compile(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.DOTALL)
HOT_DIGITS_RE = re.compile(r"\d+(?:\.\d+)?")


class BaiduHotsearchCollector(BaseCollector):
    source_platform = "baidu"
    source_type = "hotsearch"

    def collect(self) -> list[CollectedItem]:
        response = self.get(self.settings.baidu_hotsearch_url)
        return self.parse_html(response.text, collected_at=datetime.now())

    def parse_html(self, html: str, collected_at: datetime | None = None) -> list[CollectedItem]:
        payload = self.extract_payload(html)
        items = self.parse_payload(payload, collected_at=collected_at)
        return items or self.parse_cards(html, collected_at=collected_at)

    def parse_payload(self, payload: dict[str, Any], collected_at: datetime | None = None) -> list[CollectedItem]:
        rows = self._extract_rows(payload)
        collected_time = collected_at or datetime.now()
        items: list[CollectedItem] = []
        for row in rows:
            title = self._pick_first(row, "word", "title", "query")
            if not title:
                continue
            summary = self._pick_first(row, "desc", "summary")
            rank = self._pick_int(row, "rank", "index", "show")
            hot_score = self._pick_hot_score(row)
            url = self._build_url(title, self._pick_first(row, "url"))
            item_payload = {
                "provider": "baidu",
                "rank": rank,
                "hot_score": hot_score,
                "item": row,
            }
            tag = self._pick_first(row, "icon_desc", "category", "label_name", "topic")
            if tag:
                item_payload["tag"] = tag
            items.append(
                CollectedItem(
                    source_platform=self.source_platform,
                    source_type=self.source_type,
                    external_id=title,
                    title=title,
                    summary=summary,
                    url=url,
                    fallback_url=url,
                    published_at=None,
                    collected_at=collected_time,
                    raw_payload=item_payload,
                )
            )
        return items

    def parse_cards(self, html: str, collected_at: datetime | None = None) -> list[CollectedItem]:
        soup = BeautifulSoup(html, "html.parser")
        collected_time = collected_at or datetime.now()
        items: list[CollectedItem] = []
        seen_titles: set[str] = set()
        for card in soup.select(".category-wrap_iQLoo, .c-single-text-ellipsis, [class*='category-wrap']"):
            title_node = card.select_one(".c-single-text-ellipsis, .title_dIF3B, .word_XuQ0m")
            title = title_node.get_text(" ", strip=True) if title_node else card.get_text(" ", strip=True)
            title = title.strip()
            if not title or title in seen_titles:
                continue
            seen_titles.add(title)
            summary_node = card.select_one(".hot-desc_1m_jR, .desc_GAU2l, .content_1YWBm")
            rank_node = card.select_one("div[class*='index']")
            hot_node = card.select_one("div[class*='hot-index'], span[class*='hot-index'], div[class*='heat']")
            rank = self._extract_number(rank_node.get_text(" ", strip=True) if rank_node else None)
            hot_score = self._extract_number(hot_node.get_text(" ", strip=True) if hot_node else None)
            url = self._build_url(title, None)
            items.append(
                CollectedItem(
                    source_platform=self.source_platform,
                    source_type=self.source_type,
                    external_id=title,
                    title=title,
                    summary=summary_node.get_text(" ", strip=True) if summary_node else None,
                    url=url,
                    fallback_url=url,
                    collected_at=collected_time,
                    raw_payload={
                        "provider": "baidu",
                        "rank": rank,
                        "hot_score": hot_score,
                        "from_html": True,
                    },
                )
            )
        return items

    def extract_payload(self, html: str) -> dict[str, Any]:
        match = NEXT_DATA_PATTERN.search(html)
        if not match:
            return {}
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            return {}

    def _extract_rows(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[Any] = [payload]
        while candidates:
            current = candidates.pop(0)
            if isinstance(current, dict):
                for key in ("cards", "list", "items", "data", "content", "queries"):
                    value = current.get(key)
                    if isinstance(value, list) and value and isinstance(value[0], dict):
                        if any(self._pick_first(row, "word", "title", "query") for row in value if isinstance(row, dict)):
                            return [row for row in value if isinstance(row, dict)]
                        candidates.append(value)
                    elif isinstance(value, dict):
                        candidates.append(value)
                candidates.extend(v for v in current.values() if isinstance(v, dict | list))
            elif isinstance(current, list):
                dict_rows = [row for row in current if isinstance(row, dict)]
                if dict_rows and any(self._pick_first(row, "word", "title", "query") for row in dict_rows):
                    return dict_rows
                candidates.extend(dict_rows)
        return []

    def _build_url(self, title: str, existing: str | None) -> str:
        if existing and existing.startswith("http"):
            return existing
        return f"https://www.baidu.com/s?wd={quote(title)}"

    def _pick_first(self, row: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = row.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    def _pick_int(self, row: dict[str, Any], *keys: str) -> int | None:
        for key in keys:
            number = self._extract_number(row.get(key))
            if number is not None:
                return int(number)
        return None

    def _pick_hot_score(self, row: dict[str, Any]) -> int | None:
        for key in ("hotScore", "hot_index", "hotIndex", "hot_score", "heat_score"):
            number = self._extract_number(row.get(key))
            if number is not None:
                return int(number)
        return None

    def _extract_number(self, value: object) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        match = HOT_DIGITS_RE.search(str(value).replace(",", ""))
        if not match:
            return None
        return float(match.group(0))
