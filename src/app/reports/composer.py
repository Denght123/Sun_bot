from __future__ import annotations

from app.reports.contracts import (
    FULL_REPORT_BLOCK_LIMITS,
    FULL_REPORT_SECTION_ORDER,
    MAX_DAILY_MESSAGE_CHUNKS,
    MAX_LINKS_IN_FULL_REPORT,
    REPORT_DISCLAIMER,
    SECTION_CHUNK_MAX_CHARS,
    TARGET_MAX_CHARS,
    TARGET_MIN_CHARS,
    GeneratedReportBundle,
    SectionDraft,
)


class ReportComposer:
    def compose(self, *, report_date, sections: list[SectionDraft], fallback_used: bool, warnings: list[str]) -> GeneratedReportBundle:
        section_map = {section.section_key: section for section in sections}
        full_blocks = [f"【基金理财热点早报】 {report_date.isoformat()}"]
        link_entries: list[str] = []

        for section_key in FULL_REPORT_SECTION_ORDER:
            section = section_map.get(section_key)
            if section is None:
                continue
            block = self._trim_block(section.brief_block, FULL_REPORT_BLOCK_LIMITS[section_key])
            full_blocks.append(block)
            link_entries.extend(self._build_section_links(section))

        link_chunk = self._build_link_chunk(link_entries)
        full_blocks.append(link_chunk)
        disclaimer_chunk = f"【免责声明】\n{REPORT_DISCLAIMER}"
        full_blocks.append(disclaimer_chunk)

        full_text = "\n\n".join(block for block in full_blocks if block)
        full_text = self._fit_text_budget(full_text)
        message_chunks = self._split_full_text(full_text)
        if len(message_chunks) > MAX_DAILY_MESSAGE_CHUNKS:
            full_text = self._compact_text(full_text)
            message_chunks = self._split_full_text(full_text)
        if len(message_chunks) > MAX_DAILY_MESSAGE_CHUNKS:
            message_chunks = ["\n\n".join(message_chunks[:-1]), message_chunks[-1]]
            message_chunks = [chunk for chunk in message_chunks if chunk.strip()]
            full_text = "\n\n".join(message_chunks)

        detail_sections = [self._with_split_chunks(section) for section in sections]
        link_bundle = {
            "report_date": report_date.isoformat(),
            "message_chunks": message_chunks,
            "sections": {
                section.section_key: {
                    "title": section.title,
                    "links": self._build_section_links(section),
                    "render_mode": section.render_mode,
                }
                for section in detail_sections
                if section.section_key != "help"
            },
            "warnings": warnings,
        }
        generation_status = "success" if not fallback_used else "fallback_success"
        return GeneratedReportBundle(
            report_date=report_date,
            full_text=full_text,
            message_chunks=message_chunks,
            total_word_count=len(full_text),
            total_message_chunks=len(message_chunks),
            link_bundle=link_bundle,
            sections=detail_sections,
            generation_status=generation_status,
            fallback_used=fallback_used,
            warnings=warnings,
        )

    def _with_split_chunks(self, section: SectionDraft) -> SectionDraft:
        chunks = self._split_section_text(section.content)
        return SectionDraft(
            section_key=section.section_key,
            title=section.title,
            events=section.events,
            content=section.content,
            brief_block=section.brief_block,
            message_chunks=chunks,
            render_mode=section.render_mode,
        )

    def _build_section_links(self, section: SectionDraft) -> list[str]:
        links: list[str] = []
        seen: set[str] = set()
        for event in section.events:
            for link in event.source_links:
                if link in seen:
                    continue
                seen.add(link)
                links.append(link)
                if len(links) >= MAX_LINKS_IN_FULL_REPORT:
                    return links
        return links

    def _build_link_chunk(self, links: list[str]) -> str:
        unique_links: list[str] = []
        seen: set[str] = set()
        for link in links:
            if link in seen:
                continue
            seen.add(link)
            unique_links.append(link)
            if len(unique_links) >= MAX_LINKS_IN_FULL_REPORT:
                break
        if not unique_links:
            return "【原文链接集合】\n暂无可用链接。"
        lines = ["【原文链接集合】"]
        for index, link in enumerate(unique_links, start=1):
            lines.append(f"{index}. {link}")
        return "\n".join(lines)

    def _split_section_text(self, text: str) -> list[str]:
        return self._split_preserving_lines(text, SECTION_CHUNK_MAX_CHARS)

    def _split_full_text(self, text: str) -> list[str]:
        return self._split_preserving_lines(text, SECTION_CHUNK_MAX_CHARS)

    def _split_preserving_lines(self, text: str, max_chars: int) -> list[str]:
        lines = text.splitlines()
        chunks: list[str] = []
        current: list[str] = []
        current_len = 0
        for line in lines:
            line_len = len(line) + (1 if current else 0)
            if current and current_len + line_len > max_chars:
                chunks.append("\n".join(current).strip())
                current = [line]
                current_len = len(line)
                continue
            current.append(line)
            current_len += line_len
        if current:
            chunks.append("\n".join(current).strip())
        return [chunk for chunk in chunks if chunk]

    def _trim_block(self, text: str, max_chars: int) -> str:
        if len(text) <= max_chars:
            return text
        lines = text.splitlines()
        header = lines[0] if lines else ""
        body = []
        current_len = len(header)
        for line in lines[1:]:
            projected = current_len + len(line) + 1
            if projected > max_chars:
                break
            body.append(line)
            current_len = projected
        return "\n".join([header, *body]).strip()

    def _fit_text_budget(self, text: str) -> str:
        if len(text) <= TARGET_MAX_CHARS:
            return text
        return self._compact_text(text)

    def _compact_text(self, text: str) -> str:
        lines = text.splitlines()
        compacted: list[str] = []
        for line in lines:
            if len(line) > 120 and line.startswith(tuple(f"{index}." for index in range(1, 10))):
                compacted.append(line[:116].rstrip("。；，, ") + "。")
            else:
                compacted.append(line)
        compact_text = "\n".join(compacted)
        if len(compact_text) > TARGET_MAX_CHARS:
            compact_text = compact_text[: TARGET_MAX_CHARS - 1].rstrip() + "…"
        if len(compact_text) < TARGET_MIN_CHARS:
            return compact_text
        return compact_text
