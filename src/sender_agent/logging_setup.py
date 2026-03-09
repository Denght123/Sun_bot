from __future__ import annotations

import logging
from logging.config import dictConfig
from pathlib import Path

DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s [%(service_name)s] %(name)s - %(message)s"


class ServiceNameFilter(logging.Filter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def filter(self, record: logging.LogRecord) -> bool:
        record.service_name = self.service_name
        return True


class SecretMaskingFilter(logging.Filter):
    def __init__(self, secrets: list[str] | None = None) -> None:
        super().__init__()
        self.secrets = [secret for secret in secrets or [] if secret]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self.secrets:
            message = message.replace(secret, "***")
        record.msg = message
        record.args = ()
        return True


def configure_logging(*, service_name: str, log_level: str, log_file: Path, secrets: list[str] | None = None) -> None:
    log_file.parent.mkdir(parents=True, exist_ok=True)
    level_name = log_level.upper()
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "service_name": {
                    "()": "sender_agent.logging_setup.ServiceNameFilter",
                    "service_name": service_name,
                },
                "masking": {
                    "()": "sender_agent.logging_setup.SecretMaskingFilter",
                    "secrets": secrets or [],
                },
            },
            "formatters": {
                "standard": {
                    "format": DEFAULT_LOG_FORMAT,
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "level": level_name,
                    "formatter": "standard",
                    "filters": ["service_name", "masking"],
                },
                "file": {
                    "class": "logging.FileHandler",
                    "filename": str(log_file),
                    "encoding": "utf-8",
                    "level": level_name,
                    "formatter": "standard",
                    "filters": ["service_name", "masking"],
                },
            },
            "root": {
                "level": level_name,
                "handlers": ["default", "file"],
            },
        }
    )
