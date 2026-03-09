from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import api_router
from app.cache.redis import close_redis_client, get_redis_client
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import dispose_engine, get_engine

API_SERVICE_NAME = "api-service"
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    configure_logging(service_name=API_SERVICE_NAME, log_level=settings.log_level)
    logger.info("Starting API service")
    get_engine()
    get_redis_client()
    try:
        yield
    finally:
        close_redis_client()
        dispose_engine()
        logger.info("Stopping API service")


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        description=settings.app_description,
        version=settings.app_version,
        lifespan=lifespan,
    )
    application.include_router(api_router, prefix=settings.api_prefix)
    return application


app = create_app()
