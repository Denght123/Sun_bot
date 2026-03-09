from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.reports.contracts import BANNED_ADVICE_PHRASES, SectionDraft, contains_investment_advice


@dataclass(slots=True)
class LLMSectionCandidate:
    section_key: str
    content: str
    event_keys: list[str]


class ReportLLMClient(Protocol):
    def summarize_sections(self, *, report_date: str, section_payloads: dict[str, list[dict[str, object]]]) -> list[LLMSectionCandidate]:
        raise NotImplementedError


class ReportLLMOverlay:
    def __init__(self, client: ReportLLMClient | None = None) -> None:
        self.client = client

    def apply(self, *, report_date: str, template_sections: list[SectionDraft]) -> tuple[list[SectionDraft], bool, list[str]]:
        if self.client is None:
            return template_sections, True, ["llm_not_configured"]

        payloads = {
            section.section_key: [
                {
                    "event_key": event.event_key,
                    "title": event.title,
                    "source_count": event.source_count,
                    "heat_score": str(event.heat_score),
                }
                for event in section.events
            ]
            for section in template_sections
            if section.section_key != "help" and section.events
        }
        if not payloads:
            return template_sections, False, []

        try:
            candidates = self.client.summarize_sections(report_date=report_date, section_payloads=payloads)
        except Exception as exc:
            return template_sections, True, [f"llm_error:{exc}"]

        replacement_map: dict[str, SectionDraft] = {section.section_key: section for section in template_sections}
        warnings: list[str] = []
        fallback_used = False
        applied_sections: set[str] = set()

        for candidate in candidates:
            section = replacement_map.get(candidate.section_key)
            if section is None:
                warnings.append(f"unknown_section:{candidate.section_key}")
                fallback_used = True
                continue
            if not self._is_valid_candidate(section=section, candidate=candidate):
                warnings.append(f"invalid_section:{candidate.section_key}")
                fallback_used = True
                continue
            replacement_map[candidate.section_key] = SectionDraft(
                section_key=section.section_key,
                title=section.title,
                events=section.events,
                content=candidate.content,
                brief_block=candidate.content,
                message_chunks=[candidate.content],
                render_mode="hybrid",
            )
            applied_sections.add(candidate.section_key)

        missing_sections = sorted(set(payloads) - applied_sections)
        if missing_sections:
            warnings.extend(f"missing_section:{section_key}" for section_key in missing_sections)
            fallback_used = True

        ordered_sections = [replacement_map[section.section_key] for section in template_sections]
        return ordered_sections, fallback_used, warnings

    def _is_valid_candidate(self, *, section: SectionDraft, candidate: LLMSectionCandidate) -> bool:
        text = candidate.content.strip()
        if not text:
            return False
        if contains_investment_advice(text):
            return False
        if any(phrase in text for phrase in BANNED_ADVICE_PHRASES):
            return False
        if "事实：" not in text or "影响：" not in text:
            return False
        expected_keys = {event.event_key for event in section.events}
        if candidate.event_keys and not set(candidate.event_keys).issubset(expected_keys):
            return False
        return True
