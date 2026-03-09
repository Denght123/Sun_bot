from __future__ import annotations

from app.reports.composer import ReportComposer
from app.reports.contracts import DETAIL_SECTION_ORDER, GeneratedReportBundle, SECTION_TITLE_MAP
from app.reports.llm_overlay import ReportLLMClient, ReportLLMOverlay
from app.reports.repository import ReportRepository
from app.reports.selector import ReportSelector
from app.reports.template_engine import ReportTemplateEngine


class ReportAssembler:
    def __init__(self, repository: ReportRepository, llm_client: ReportLLMClient | None = None) -> None:
        self.repository = repository
        self.selector = ReportSelector()
        self.template_engine = ReportTemplateEngine()
        self.llm_overlay = ReportLLMOverlay(llm_client)
        self.composer = ReportComposer()

    def build(self, *, candidate_feed) -> GeneratedReportBundle:
        selected_sections = self.selector.select(candidate_feed)
        projection = self.selector.build_full_report_projection(selected_sections)

        template_sections = [
            self.template_engine.render_section(
                section_key=section_key,
                events=projection.get(section_key, []) if section_key == "overview" else selected_sections.get(section_key, []),
                detail=True,
            )
            for section_key in DETAIL_SECTION_ORDER
        ]
        llm_sections, fallback_used, warnings = self.llm_overlay.apply(
            report_date=candidate_feed.report_date.isoformat(),
            template_sections=template_sections,
        )
        full_bundle = self.composer.compose(
            report_date=candidate_feed.report_date,
            sections=[
                self._rewrite_brief_block(section)
                if section.section_key in projection and section.section_key != "help"
                else section
                for section in llm_sections
            ],
            fallback_used=fallback_used,
            warnings=warnings,
        )
        help_section = self.template_engine.build_help_section()
        full_bundle.sections.append(help_section)
        return full_bundle

    def _rewrite_brief_block(self, section):
        return section
