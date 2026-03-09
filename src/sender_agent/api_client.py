from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import requests
from pydantic import ValidationError

from sender_agent.config import SenderSettings
from sender_agent.errors import SenderApiError, SenderNetworkError
from sender_agent.models import (
    ContentMenuPayload,
    PendingDispatchTask,
    PendingDispatchTasksData,
    ResponseEnvelope,
    SenderEventPayload,
    SenderHeartbeatPayload,
    SenderHeartbeatResponseData,
    SenderTaskResultPayload,
    SenderTaskResultResponseData,
)

logger = logging.getLogger(__name__)


class SenderApiClient:
    def __init__(self, settings: SenderSettings) -> None:
        self.settings = settings
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {settings.sender_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def close(self) -> None:
        self.session.close()

    def send_heartbeat(self, payload: SenderHeartbeatPayload) -> SenderHeartbeatResponseData:
        data = self._request("POST", "sender/heartbeat", json_body=payload.model_dump(mode="json"))
        return self._parse_model(SenderHeartbeatResponseData, data, context="heartbeat response")

    def fetch_pending_tasks(self, *, sender_id: str, limit: int) -> list[PendingDispatchTask]:
        data = self._request(
            "GET",
            "sender/tasks/pending",
            params={"sender_id": sender_id, "limit": limit},
        )
        tasks_data = self._parse_model(PendingDispatchTasksData, data, context="pending tasks")
        return tasks_data.tasks

    def report_task_result(self, task_id: str, payload: SenderTaskResultPayload) -> SenderTaskResultResponseData:
        data = self._request(
            "POST",
            f"sender/tasks/{task_id}/result",
            json_body=payload.model_dump(mode="json"),
        )
        return self._parse_model(SenderTaskResultResponseData, data, context="task result response")

    def report_event(self, payload: SenderEventPayload) -> dict[str, Any]:
        data = self._request("POST", "sender/events", json_body=payload.model_dump(mode="json"))
        return data or {}

    def get_content_menu(self, *, keyword: str, report_date: str | None = None) -> ContentMenuPayload:
        params: dict[str, str] = {"keyword": keyword}
        if report_date:
            params["report_date"] = report_date
        data = self._request("GET", "content/menu", params=params)
        return self._parse_model(ContentMenuPayload, data, context="content menu")

    def _parse_model(self, model_type: Any, data: Any, *, context: str) -> Any:
        try:
            return model_type.model_validate(data or {})
        except ValidationError as exc:
            raise SenderApiError(f"Cloud API returned invalid {context} payload: {exc}") from exc

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> Any:
        url = self._build_url(path)
        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_body,
                timeout=self.settings.request_timeout_seconds,
            )
        except requests.RequestException as exc:
            raise SenderNetworkError(f"Request to cloud API failed: {exc}") from exc

        envelope = self._parse_envelope(response)
        if response.status_code >= 400:
            raise SenderApiError(
                envelope.message,
                code=envelope.code,
                status_code=response.status_code,
            )
        if envelope.code != 0:
            raise SenderApiError(
                envelope.message,
                code=envelope.code,
                status_code=response.status_code,
            )
        return envelope.data

    def _build_url(self, path: str) -> str:
        normalized_base = f"{self.settings.api_base_url.rstrip('/')}/"
        return urljoin(normalized_base, path.lstrip("/"))

    def _parse_envelope(self, response: requests.Response) -> ResponseEnvelope:
        try:
            payload = response.json()
        except ValueError as exc:
            logger.error("Cloud API returned invalid JSON with status=%s", response.status_code)
            raise SenderApiError(
                f"Cloud API returned invalid JSON: {response.text[:200]}",
                status_code=response.status_code,
            ) from exc
        return ResponseEnvelope.model_validate(payload)
