from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from sender_agent import __version__
from sender_agent.errors import SenderConfigError


@dataclass(slots=True)
class SenderSettings:
    api_base_url: str
    sender_token: str
    sender_id: str
    timezone: str
    log_level: str
    heartbeat_interval_seconds: int
    poll_interval_seconds: int
    request_timeout_seconds: int
    task_limit: int
    client_version: str
    local_state_dir: Path
    log_file: Path
    journal_path: Path
    wechat_window_title_hint: str
    wechat_send_delay_ms: int
    wechat_chat_search_timeout_seconds: int
    heartbeat_ip: str | None = None


_REQUIRED_ENV_VARS = {
    "SENDER_API_BASE_URL": "cloud API base URL",
    "SENDER_TOKEN": "sender bearer token",
    "SENDER_ID": "sender unique identifier",
}


def load_settings(env_file: str | None = None) -> SenderSettings:
    load_dotenv(dotenv_path=env_file or ".env", override=False)

    missing = [key for key in _REQUIRED_ENV_VARS if not os.getenv(key)]
    if missing:
        details = ", ".join(f"{key} ({_REQUIRED_ENV_VARS[key]})" for key in missing)
        raise SenderConfigError(f"Missing required sender environment variables: {details}")

    state_dir = Path(os.getenv("SENDER_LOCAL_STATE_DIR", Path.home() / ".finance-news-bot-sender")).expanduser()
    state_dir.mkdir(parents=True, exist_ok=True)

    log_file = Path(os.getenv("SENDER_LOG_FILE", state_dir / "sender-agent.log")).expanduser()
    journal_path = Path(os.getenv("SENDER_JOURNAL_PATH", state_dir / "sender-agent.sqlite3")).expanduser()

    return SenderSettings(
        api_base_url=os.environ["SENDER_API_BASE_URL"].rstrip("/"),
        sender_token=os.environ["SENDER_TOKEN"],
        sender_id=os.environ["SENDER_ID"],
        timezone=os.getenv("SENDER_TIMEZONE", "Asia/Shanghai"),
        log_level=os.getenv("SENDER_LOG_LEVEL", "INFO"),
        heartbeat_interval_seconds=max(5, int(os.getenv("SENDER_HEARTBEAT_INTERVAL_SEC", "30"))),
        poll_interval_seconds=max(3, int(os.getenv("SENDER_POLL_INTERVAL_SEC", "5"))),
        request_timeout_seconds=max(3, int(os.getenv("SENDER_REQUEST_TIMEOUT_SEC", "10"))),
        task_limit=max(1, min(1, int(os.getenv("SENDER_TASK_LIMIT", "1")))),
        client_version=os.getenv("SENDER_CLIENT_VERSION", __version__),
        local_state_dir=state_dir,
        log_file=log_file,
        journal_path=journal_path,
        wechat_window_title_hint=os.getenv("WECHAT_WINDOW_TITLE_HINT", "微信"),
        wechat_send_delay_ms=max(0, int(os.getenv("WECHAT_SEND_DELAY_MS", "300"))),
        wechat_chat_search_timeout_seconds=max(1, int(os.getenv("WECHAT_CHAT_SEARCH_TIMEOUT_SEC", "10"))),
        heartbeat_ip=os.getenv("SENDER_HEARTBEAT_IP") or None,
    )
