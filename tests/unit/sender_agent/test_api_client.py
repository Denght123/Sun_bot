from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
import requests

from sender_agent.api_client import SenderApiClient
from sender_agent.config import SenderSettings
from sender_agent.errors import SenderApiError, SenderNetworkError


def build_settings() -> SenderSettings:
    return SenderSettings(
        api_base_url="http://127.0.0.1:8000/api",
        sender_token="token-123",
        sender_id="sender-01",
        timezone="Asia/Shanghai",
        log_level="INFO",
        heartbeat_interval_seconds=30,
        poll_interval_seconds=5,
        request_timeout_seconds=10,
        task_limit=1,
        client_version="0.1.0",
        local_state_dir=Path("."),
        log_file=Path("sender.log"),
        journal_path=Path("sender.sqlite3"),
        wechat_window_title_hint="微信",
        wechat_send_delay_ms=300,
        wechat_chat_search_timeout_seconds=10,
        heartbeat_ip=None,
    )


def build_response(*, status_code: int = 200, payload=None, text: str = ""):
    response = Mock(spec=requests.Response)
    response.status_code = status_code
    response.text = text
    response.json = Mock(return_value=payload)
    return response


def test_sender_api_client_builds_urls_without_double_slashes() -> None:
    client = SenderApiClient(build_settings())
    try:
        assert client._build_url("sender/heartbeat") == "http://127.0.0.1:8000/api/sender/heartbeat"
        assert client._build_url("/sender/tasks/pending") == "http://127.0.0.1:8000/api/sender/tasks/pending"
    finally:
        client.close()


def test_request_raises_network_error_on_request_exception() -> None:
    client = SenderApiClient(build_settings())
    client.session.request = Mock(side_effect=requests.RequestException("boom"))

    try:
        with pytest.raises(SenderNetworkError, match="Request to cloud API failed"):
            client._request("GET", "sender/tasks/pending")
    finally:
        client.close()


def test_request_raises_api_error_for_http_error_response() -> None:
    client = SenderApiClient(build_settings())
    client.session.request = Mock(
        return_value=build_response(
            status_code=409,
            payload={"code": 1001, "message": "task status conflict", "data": None},
        )
    )

    try:
        with pytest.raises(SenderApiError, match="task status conflict") as exc_info:
            client._request("POST", "sender/tasks/task-1/result")
        assert exc_info.value.status_code == 409
        assert exc_info.value.code == 1001
    finally:
        client.close()


def test_request_raises_api_error_for_invalid_json() -> None:
    client = SenderApiClient(build_settings())
    response = Mock(spec=requests.Response)
    response.status_code = 502
    response.text = "bad gateway"
    response.json = Mock(side_effect=ValueError("not json"))
    client.session.request = Mock(return_value=response)

    try:
        with pytest.raises(SenderApiError, match="invalid JSON"):
            client._request("GET", "sender/tasks/pending")
    finally:
        client.close()


def test_fetch_pending_tasks_raises_api_error_for_invalid_payload_shape() -> None:
    client = SenderApiClient(build_settings())
    client.session.request = Mock(
        return_value=build_response(
            payload={"code": 0, "message": "ok", "data": {"tasks": [{"task_id": "task-1"}]}}
        )
    )

    try:
        with pytest.raises(SenderApiError, match="invalid pending tasks payload"):
            client.fetch_pending_tasks(sender_id="sender-01", limit=1)
    finally:
        client.close()
