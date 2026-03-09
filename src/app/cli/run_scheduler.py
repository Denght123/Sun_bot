from __future__ import annotations

import logging
import signal
from threading import Event

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.scheduler.bootstrap import SCHEDULER_SERVICE_NAME, start_scheduler

logger = logging.getLogger(__name__)
shutdown_event = Event()


def _handle_shutdown(_: int, __) -> None:
    shutdown_event.set()


def main() -> None:
    settings = get_settings()
    configure_logging(service_name=SCHEDULER_SERVICE_NAME, log_level=settings.log_level)
    scheduler = start_scheduler()
    if scheduler is None:
        logger.info("Scheduler process exiting because scheduling is disabled")
        return

    signal.signal(signal.SIGINT, _handle_shutdown)
    signal.signal(signal.SIGTERM, _handle_shutdown)
    logger.info("Scheduler process is running")
    shutdown_event.wait()
    scheduler.shutdown(wait=False)
    logger.info("Scheduler process stopped")


if __name__ == "__main__":
    main()
