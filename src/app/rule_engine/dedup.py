from __future__ import annotations

import re
from collections.abc import Iterable

from app.parser_normalizer.schemas import NormalizedRawItem

NON_WORD_RE = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff]+")


def deduplicate_items(items: list[NormalizedRawItem]) -> list[NormalizedRawItem]:
    deduplicated: list[NormalizedRawItem] = []
    seen_keys: set[str] = set()
    for item in items:
        keys = exact_dedup_keys(item)
        if any(key in seen_keys for key in keys):
            continue
        seen_keys.update(keys)
        deduplicated.append(item)
    return deduplicated


def exact_dedup_keys(item: NormalizedRawItem) -> list[str]:
    keys: list[str] = [f"hash:{item.content_hash}"]
    if item.external_id:
        keys.insert(0, f"external:{item.source_platform}:{item.external_id}")
    if item.canonical_url:
        keys.append(f"url:{item.canonical_url}")
    elif item.url:
        keys.append(f"url:{item.url}")
    return keys


def normalize_title_for_match(title: str) -> str:
    return NON_WORD_RE.sub("", title).lower().strip()


def tokenize_for_similarity(text: str) -> set[str]:
    normalized = normalize_title_for_match(text)
    if not normalized:
        return set()
    tokens: set[str] = set()
    ascii_parts = re.findall(r"[a-z0-9]+", normalized)
    tokens.update(ascii_parts)
    chinese_only = re.sub(r"[a-z0-9]", "", normalized)
    if len(chinese_only) <= 2:
        if chinese_only:
            tokens.add(chinese_only)
    else:
        tokens.update(chinese_only[index : index + 2] for index in range(len(chinese_only) - 1))
    if not tokens:
        tokens.add(normalized)
    return tokens


def jaccard_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    intersection = len(left_set & right_set)
    union = len(left_set | right_set)
    if union == 0:
        return 0.0
    return intersection / union


def title_similarity(left: str, right: str) -> float:
    if normalize_title_for_match(left) == normalize_title_for_match(right):
        return 1.0
    return jaccard_similarity(tokenize_for_similarity(left), tokenize_for_similarity(right))


def keyword_overlap(left: str, right: str) -> float:
    return jaccard_similarity(tokenize_for_similarity(left), tokenize_for_similarity(right))
