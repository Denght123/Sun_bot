from __future__ import annotations

import logging

from sender_agent.agent import SenderAgent
from sender_agent.api_client import SenderApiClient
from sender_agent.config import load_settings
from sender_agent.errors import SenderConfigError
from sender_agent.executor import TaskExecutor
from sender_agent.logging_setup import configure_logging
from sender_agent.task_journal import TaskJournal
from sender_agent.wechat.windows_uia_adapter import WindowsUiaWechatAutomation

logger = logging.getLogger(__name__)


def main() -> int:
    try:
        settings = load_settings()
    except SenderConfigError as exc:
        print(f"Sender configuration error: {exc}")
        return 2

    configure_logging(
        service_name="sender-agent",
        log_level=settings.log_level,
        log_file=settings.log_file,
        secrets=[settings.sender_token],
    )

    wechat = WindowsUiaWechatAutomation(
        window_title_hint=settings.wechat_window_title_hint,
        send_delay_ms=settings.wechat_send_delay_ms,
        search_timeout_seconds=settings.wechat_chat_search_timeout_seconds,
    )
    task_journal = TaskJournal(settings.journal_path)
    api_client = SenderApiClient(settings)
    executor = TaskExecutor(
        settings=settings,
        api_client=api_client,
        task_journal=task_journal,
        wechat=wechat,
    )
    agent = SenderAgent(
        settings=settings,
        api_client=api_client,
        task_journal=task_journal,
        executor=executor,
        wechat=wechat,
    )

    logger.info("Starting sender agent sender_id=%s api_base_url=%s", settings.sender_id, settings.api_base_url)
    agent.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
