from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

import requests
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.time import now_in_timezone
from app.core.time_window import build_report_window
from app.db.model_definitions import DailyReport
from app.reports.composer import ReportComposer
from app.reports.contracts import DETAIL_SECTION_ORDER, GeneratedReportBundle
from app.reports.llm_overlay import LLMSectionCandidate, ReportLLMClient, ReportLLMOverlay
from app.reports.repository import ReportRepository
from app.reports.selector import ReportSelector
from app.reports.template_engine import ReportTemplateEngine


@dataclass(slots=True)
class ReportGenerationResult:
    report: DailyReport
    warnings: list[str]


class ConfiguredReportLLMClient(ReportLLMClient):
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def summarize_sections(self, *, report_date: str, section_payloads: dict[str, list[dict[str, object]]]) -> list[LLMSectionCandidate]:
        if not self.settings.llm_api_url or not self.settings.llm_api_key or not self.settings.llm_model:
            raise RuntimeError("llm_not_configured")

        payload = {
            "model": self.settings.llm_model,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是基金理财热点消息机器人的摘要模块。"
                        "必须输出 JSON，且文案必须先事实、后影响，中性克制，不输出投资建议。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "report_date": report_date,
                            "instruction": {
                                "style": "先事实后影响，中性克制",
                                "forbidden": ["投资建议", "买入", "卖出", "加仓", "减仓"],
                                "required_format": "每个 section 的 content 都需要包含 事实： 和 影响：",
                            },
                            "sections": section_payloads,
                            "output_schema": {
                                "sections": [
                                    {
                                        "section_key": "sector",
                                        "content": "【板块观察】\\n1. 事实：...。影响：...",
                                        "event_keys": ["event-1"],
                                    }
                                ]
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        response = requests.post(
            self.settings.llm_api_url,
            headers=headers,
            json=payload,
            timeout=self.settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        response_data = response.json()
        parsed = self._parse_response(response_data)
        candidates: list[LLMSectionCandidate] = []
        for item in parsed:
            if not isinstance(item, dict):
                continue
            section_key = item.get("section_key")
            content = item.get("content")
            event_keys = item.get("event_keys") or []
            if not isinstance(section_key, str) or not isinstance(content, str):
                continue
            candidates.append(
                LLMSectionCandidate(
                    section_key=section_key,
                    content=content,
                    event_keys=[str(key) for key in event_keys if isinstance(key, str)],
                )
            )
        return candidates

    def _parse_response(self, response_data: dict[str, object]) -> list[dict[str, object]]:
        if "choices" in response_data:
            choices = response_data.get("choices")
            if not isinstance(choices, list) or not choices:
                raise RuntimeError("llm_empty_choices")
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            if not isinstance(message, dict) or not isinstance(message.get("content"), str):
                raise RuntimeError("llm_missing_message_content")
            content = message["content"]
            payload = json.loads(content)
        else:
            payload = response_data

        sections = payload.get("sections") if isinstance(payload, dict) else None
        if not isinstance(sections, list):
            raise RuntimeError("llm_invalid_sections")
        return [item for item in sections if isinstance(item, dict)]


class ReportGeneratorService:
    def __init__(self, session: Session, settings: Settings | None = None, llm_client: ReportLLMClient | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.repository = ReportRepository(session)
        self.selector = ReportSelector()
        self.template_engine = ReportTemplateEngine()
        self.composer = ReportComposer()
        self.llm_overlay = ReportLLMOverlay(llm_client or self._build_llm_client())

    def find_existing(self, report_date: date) -> DailyReport | None:
        return self.repository.find_report(report_date)

    def build_message_chunks(self, report: DailyReport) -> list[str]:
        link_bundle = report.link_bundle or {}
        chunks = link_bundle.get("message_chunks")
        if isinstance(chunks, list):
            return [str(chunk) for chunk in chunks if isinstance(chunk, str)]
        if report.full_text:
            return [report.full_text]
        return []

    def get_or_generate(self, report_date: date, force_regenerate: bool = False) -> ReportGenerationResult:
        report = self.find_existing(report_date)
        if report is not None and report.generation_status in {"success", "fallback_success"} and not force_regenerate:
            warnings = []
            if isinstance(report.link_bundle, dict):
                warnings = [str(item) for item in report.link_bundle.get("warnings", []) if isinstance(item, str)]
            return ReportGenerationResult(report=report, warnings=warnings)
        return self.generate(report_date=report_date, existing_report=report)

    def generate(self, report_date: date, existing_report: DailyReport | None = None) -> ReportGenerationResult:
        target = existing_report or self._build_report_shell(report_date)
        window = build_report_window(report_date, self.settings.timezone)
        target.generation_status = "processing"
        target.fallback_used = False
        target.last_error = None
        target.data_window_start = window.start
        target.data_window_end = window.end
        self.session.add(target)
        self.session.flush()

        try:
            bundle = self._build_report_bundle(report_date)
        except Exception as exc:
            target.generation_status = "failed"
            target.last_error = str(exc)
            self.session.flush()
            raise

        target.full_text = bundle.full_text
        target.link_bundle = bundle.link_bundle
        target.total_word_count = bundle.total_word_count
        target.total_message_chunks = bundle.total_message_chunks
        target.generated_at = now_in_timezone()
        target.generation_status = bundle.generation_status
        target.fallback_used = bundle.fallback_used
        target.last_error = None
        self.repository.replace_sections(report=target, sections=bundle.sections)
        self.session.flush()
        return ReportGenerationResult(report=target, warnings=bundle.warnings)

    def build_keyword_payload(self, *, report_date: date, keyword: str) -> dict[str, object] | None:
        report = self.find_existing(report_date)
        if report is None:
            return None

        normalized_keyword = keyword.strip()
        if normalized_keyword in {"功能", "帮助"}:
            help_section = self.repository.get_section_by_key(report_date=report_date, section_key="help")
            if help_section is None:
                help_section = self.template_engine.build_help_section()
                return {
                    "keyword": normalized_keyword,
                    "title": help_section.title,
                    "content": help_section.content,
                    "message_chunks": help_section.message_chunks,
                }
            return {
                "keyword": normalized_keyword,
                "title": help_section.title,
                "content": help_section.content,
                "message_chunks": help_section.message_chunks or [help_section.content],
            }

        if normalized_keyword == "早报":
            return {
                "keyword": normalized_keyword,
                "title": "完整精简版日报",
                "content": report.full_text or "",
                "message_chunks": self.build_message_chunks(report),
            }

        section_key_map = {
            "板块": "sector",
            "政策": "policy",
            "国际": "international",
            "热搜": "hot_topics",
            "风险": "risk",
        }
        section_key = section_key_map.get(normalized_keyword)
        if section_key is None:
            return None
        section = self.repository.get_section_by_key(report_date=report_date, section_key=section_key)
        if section is None:
            return None
        return {
            "keyword": normalized_keyword,
            "title": section.title,
            "content": section.content,
            "message_chunks": section.message_chunks or [section.content],
        }

    def _build_report_shell(self, report_date: date) -> DailyReport:
        window = build_report_window(report_date, self.settings.timezone)
        report = DailyReport(
            report_date=report_date,
            generation_status="pending",
            fallback_used=False,
            data_window_start=window.start,
            data_window_end=window.end,
        )
        self.session.add(report)
        self.session.flush()
        return report

    def _build_report_bundle(self, report_date: date) -> GeneratedReportBundle:
        window = build_report_window(report_date, self.settings.timezone)
        candidate_feed = self.repository.load_candidate_feed(
            report_date=report_date,
            window_start=window.start,
            window_end=window.end,
        )
        selected_sections = self.selector.select(candidate_feed)
        full_report_projection = self.selector.build_full_report_projection(selected_sections)

        template_sections = []
        for section_key in DETAIL_SECTION_ORDER:
            detail_section = self.template_engine.render_section(
                section_key=section_key,
                events=selected_sections.get(section_key, []),
                detail=True,
            )
            brief_section = self.template_engine.render_section(
                section_key=section_key,
                events=full_report_projection.get(section_key, []),
                detail=False,
            )
            detail_section.brief_block = brief_section.brief_block
            template_sections.append(detail_section)

        llm_enabled = self.settings.llm_enabled
        sections = template_sections
        fallback_used = False
        warnings: list[str] = []
        if llm_enabled:
            sections, fallback_used, warnings = self.llm_overlay.apply(
                report_date=report_date.isoformat(),
                template_sections=template_sections,
            )
        bundle = self.composer.compose(
            report_date=report_date,
            sections=sections,
            fallback_used=fallback_used,
            warnings=warnings,
        )
        bundle.sections.append(self.template_engine.build_help_section())
        bundle.generation_status = self._resolve_generation_status(
            llm_enabled=llm_enabled,
            sections=sections,
            fallback_used=fallback_used,
        )
        bundle.fallback_used = fallback_used
        return bundle

    def _resolve_generation_status(self, *, llm_enabled: bool, sections, fallback_used: bool) -> str:
        if not llm_enabled:
            return "success"
        if not fallback_used:
            return "success"
        if any(section.render_mode == "hybrid" for section in sections):
            return "success"
        return "fallback_success"

    def _build_llm_client(self) -> ReportLLMClient | None:
        if not self.settings.llm_enabled:
            return None
        return ConfiguredReportLLMClient(self.settings)
