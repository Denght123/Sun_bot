from __future__ import annotations

from app.reports.contracts import HELP_CONTENT, HELP_TITLE, SECTION_TITLE_MAP, SectionDraft


class ReportTemplateEngine:
    def render_section(self, *, section_key: str, events, detail: bool) -> SectionDraft:
        title = SECTION_TITLE_MAP[section_key]
        if not events:
            empty_text = self._build_empty_text(title)
            return SectionDraft(
                section_key=section_key,
                title=title,
                events=[],
                content=empty_text,
                brief_block=empty_text,
                message_chunks=[empty_text],
                render_mode="template",
            )

        if section_key == "overview":
            lines = [f"【{title}】"]
            for index, event in enumerate(events, start=1):
                lines.append(f"{index}. 事实：{event.title}。影响：市场关注度提升，需持续跟踪后续公开信息。")
            content = "\n".join(lines)
            return SectionDraft(
                section_key=section_key,
                title=title,
                events=list(events),
                content=content,
                brief_block=content,
                message_chunks=[content],
                render_mode="template",
            )

        header = f"【{title}】"
        detail_lines = [header]
        brief_lines = [header]
        for index, event in enumerate(events, start=1):
            fact = f"事实：{event.title}"
            impact = self._impact_line(section_key=section_key, event=event)
            detail_lines.append(f"{index}. {fact}。{impact}")
            brief_lines.append(f"{index}. {fact}。{impact}")

        content = "\n".join(detail_lines)
        brief_block = "\n".join(brief_lines)
        return SectionDraft(
            section_key=section_key,
            title=title,
            events=list(events),
            content=content,
            brief_block=brief_block,
            message_chunks=[content] if detail else [brief_block],
            render_mode="template",
        )

    def build_help_section(self) -> SectionDraft:
        content = f"【{HELP_TITLE}】\n{HELP_CONTENT}"
        return SectionDraft(
            section_key="help",
            title=HELP_TITLE,
            events=[],
            content=content,
            brief_block=content,
            message_chunks=[content],
            render_mode="template",
        )

    def _build_empty_text(self, title: str) -> str:
        return f"【{title}】\n暂无高置信度新增事件。"

    def _impact_line(self, *, section_key: str, event) -> str:
        if section_key == "sector":
            return f"影响：相关板块短期关注度上升，当前主要反映在题材讨论与资金预期变化上。"
        if section_key == "policy":
            return f"影响：后续需继续观察政策细则、执行节奏及对行业预期的传导。"
        if section_key == "international":
            return f"影响：海外变量可能通过汇率、风险偏好与资产定价预期传导至国内市场。"
        if section_key == "hot_topics":
            return f"影响：舆情热度上升，但仍需区分情绪传播与实际基本面变化。"
        if section_key == "risk":
            return f"影响：相关不确定性上升，需持续关注后续公告与风险暴露情况。"
        return f"影响：该事件可能影响短期市场关注重点，仍需结合后续信息观察。"
