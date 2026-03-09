from __future__ import annotations

import logging
from logging.config import dictConfig


DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s [%(service_name)s] %(name)s - %(message)s"


class ServiceNameFilter(logging.Filter):
    def __init__(self, service_name: str) -> None:
        super().__init__()
        self.service_name = service_name

    def filter(self, record: logging.LogRecord) -> bool:
        record.service_name = self.service_name
        return True


def configure_logging(service_name: str, log_level: str) -> None:
    level_name = log_level.upper()
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "service_name": {
                    "()": "app.core.logging.ServiceNameFilter",
                    "service_name": service_name,
                }
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
                    "filters": ["service_name"],
                }
            },
            "root": {
                "level": level_name,
                "handlers": ["default"],
            },
            "loggers": {
                "uvicorn": {"handlers": ["default"], "level": level_name, "propagate": False},
                "uvicorn.error": {"handlers": ["default"], "level": level_name, "propagate": False},
                "uvicorn.access": {"handlers": ["default"], "level": level_name, "propagate": False},
                "apscheduler": {"handlers": ["default"], "level": level_name, "propagate": False},
            },
        }
    )
