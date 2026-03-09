from __future__ import annotations

from pathlib import Path

import pytest

from sender_agent.config import load_settings
from sender_agent.errors import SenderConfigError


@pytest.fixture(autouse=True)
def clear_sender_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "SENDER_API_BASE_URL",
        "SENDER_TOKEN",
        "SENDER_ID",
        "SENDER_LOCAL_STATE_DIR",
        "SENDER_LOG_FILE",
        "SENDER_JOURNAL_PATH",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_load_settings_requires_core_sender_env(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(SenderConfigError):
        load_settings()


def test_load_settings_uses_local_state_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SENDER_API_BASE_URL", "http://127.0.0.1:8000/api")
    monkeypatch.setenv("SENDER_TOKEN", "token-123")
    monkeypatch.setenv("SENDER_ID", "sender-01")
    monkeypatch.setenv("SENDER_LOCAL_STATE_DIR", str(tmp_path / "state"))

    settings = load_settings()

    assert settings.sender_id == "sender-01"
    assert settings.api_base_url == "http://127.0.0.1:8000/api"
    assert settings.local_state_dir == tmp_path / "state"
    assert settings.log_file.parent == settings.local_state_dir
    assert settings.journal_path.parent == settings.local_state_dir
