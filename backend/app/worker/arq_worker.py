from arq.connections import RedisSettings

from app.core.config import get_settings

_settings = get_settings()


async def ping(ctx: dict) -> str:
    """Trivial task proving the worker is wired to Redis correctly."""
    return "pong"


class WorkerSettings:
    functions = [ping]
    redis_settings = RedisSettings.from_dsn(str(_settings.redis_url))
