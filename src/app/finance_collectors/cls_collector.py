from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from app.collectors.base import BaseCollector, CollectedItem

CLS_JSON_PATTERN = re.compile(r"telegraphList\s*=\s*(\[.*?\])\s*;", re.DOTALL)
SCRIPT_JSON_PATTERN = re.compile(r"__NEXT_DATA__\s*=\s*(\{.*?\})\s*;", re.DOTALL)
DIGITS_RE = re.compile(r"\d+")


class CLSCollector(BaseCollector):
    source_platform = "cls"
    source_type = "news"

    def collect(self) -> list[CollectedItem]:
        response = self.get(self.settings.cls_base_url)
        return self.parse_html(response.text, collected_at=datetime.now())

    def parse_html(self, html: str, collected_at: datetime | None = None) -> list[CollectedItem]:
        payload = self.extract_payload(html)
        return self.parse_payload(payload, collected_at=collected_at)

    def parse_payload(self, payload: dict[str, Any] | list[dict[str, Any]], collected_at: datetime | None = None) -> list[CollectedItem]:
        rows = self._extract_rows(payload)
        collected_time = collected_at or datetime.now()
        items: list[CollectedItem] = []
        for row in rows:
            title = self._pick_first(row, "title", "brief", "subject")
            summary = self._pick_first(row, "content", "summary", "descr", "brief")
            external_id = self._extract_id(row)
            url = self._pick_first(row, "share_url", "url", "article_url")
            published_at = self._pick_first(row, "ctime", "published_at", "created_at", "time")
            if not title and not summary:
                continue
            items.append(
                CollectedItem(
                    source_platform=self.source_platform,
                    source_type=self.source_type,
                    external_id=external_id,
                    title=title or summary or "",
                    summary=summary,
                    url=url,
                    fallback_url=url,
                    published_at=published_at,
                    collected_at=collected_time,
                    raw_payload={
                        "provider": "cls",
                        "item": row,
                    },
                )
            )
        return items

    def extract_payload(self, html: str) -> dict[str, Any] | list[dict[str, Any]]:
        for pattern in (CLS_JSON_PATTERN, SCRIPT_JSON_PATTERN):
            match = pattern.search(html)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                except json.JSONDecodeError:
                    continue
                rows = self._extract_rows(parsed)
                if rows:
                    return parsed
        raise ValueError("Unable to extract CLS telegraph payload")

    def _extract_rows(self, payload: dict[str, Any] | list[dict[str, Any]]) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        candidates: list[Any] = [payload]
        candidates.extend(payload.values())
        for candidate in candidates:
            if isinstance(candidate, dict):
                for key in ("telegraphList", "list", "items", "data", "roll_data"):
                    rows = candidate.get(key)
                    if isinstance(rows, list) and rows and isinstance(rows[0], dict):
                        return rows
            if isinstance(candidate, list) and candidate and isinstance(candidate[0], dict):
                return candidate
        return []

    def _extract_id(self, row: dict[str, Any]) -> str | None:
        for key in ("id", "news_id", "article_id", "telegraph_id"):
            value = row.get(key)
            if value is not None and str(value).strip():
                return str(value)
        share_url = self._pick_first(row, "share_url", "url", "article_url")
        if not share_url:
            return None
        match = DIGITS_RE.search(share_url)
        return match.group(0) if match else share_url

    def _pick_first(self, row: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = row.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None
