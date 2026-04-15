import redis

from config import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Get or create Redis client singleton"""
    global _client
    if _client is None:
        _client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password or None,
            db=settings.redis_db,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
        )
    return _client
