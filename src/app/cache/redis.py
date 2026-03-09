from __future__ import annotations

from functools import lru_cache

from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    settings = get_settings()
    return Redis.from_url(settings.redis_url, decode_responses=True)


def ping_redis() -> tuple[bool, str | None]:
    try:
        get_redis_client().ping()
        return True, None
    except RedisError as exc:
        return False, str(exc)


def close_redis_client() -> None:
    if get_redis_client.cache_info().currsize == 0:
        return
    get_redis_client().close()
    get_redis_client.cache_clear()
