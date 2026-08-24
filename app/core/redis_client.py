import logging

import redis.asyncio as aioredis

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_pool: aioredis.ConnectionPool | None = None


def get_redis_pool() -> aioredis.ConnectionPool:
    """
    Return the shared Redis connection pool, creating it on first use.

    Reusing a single pool across the app avoids the connection-per-call
    pattern that the previous ad-hoc `aioredis.from_url()` calls used.
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.ConnectionPool.from_url(
            settings.redis_url_str,
            decode_responses=True,
            max_connections=20,
        )
    return _redis_pool


def get_redis_client() -> aioredis.Redis:
    """Return a Redis client backed by the shared connection pool."""
    return aioredis.Redis(connection_pool=get_redis_pool())


async def close_redis_pool() -> None:
    """
    Close the shared Redis connection pool.

    Called from the FastAPI lifespan handler on application shutdown so
    connections are released cleanly instead of leaking.
    """
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.disconnect()
        _redis_pool = None


async def blacklist_token(jti: str, ttl_seconds: int | None = None) -> bool:
    """
    Add a JWT's jti to the Redis blacklist.

    TTL defaults to settings.REDIS_BLACKLIST_TTL_SECONDS, which should
    match the access token lifetime: once the JWT's own `exp` passes it
    is invalid regardless of the blacklist, so keeping the blacklist
    entry any longer than that just wastes memory.

    This call NEVER raises — Redis being unreachable at logout time
    should not prevent the user from completing the logout flow. The
    caller (AuthService.logout) still revokes the refresh token and
    session in Postgres regardless of whether the Redis write succeeds.

    Returns True if the blacklist write succeeded, False otherwise.
    """
    ttl = ttl_seconds or settings.REDIS_BLACKLIST_TTL_SECONDS
    try:
        client = get_redis_client()
        await client.setex(f"blacklist:{jti}", ttl, "1")
        return True
    except Exception:
        logger.warning(
            "Failed to blacklist jti=%s in Redis; token remains valid until "
            "its natural expiry.",
            jti,
            exc_info=True,
        )
        return False


async def is_token_blacklisted(jti: str) -> bool:
    """
    Check whether a jti is present in the Redis blacklist.

    SECURITY DECISION — fail-open by design:
    If Redis is unreachable, this returns False (token treated as NOT
    blacklisted) so that a Redis outage does not take down authentication
    for the entire platform. Access tokens are short-lived (15 minutes by
    default), which bounds the exposure window of a "revoked but Redis
    was down" token to at most one token lifetime.

    If your threat model requires fail-closed behavior (reject all
    requests when Redis is down), that should be an explicit, configurable
    trade-off — not an accident. Track it as hardening work if needed.
    """
    try:
        client = get_redis_client()
        return bool(await client.exists(f"blacklist:{jti}"))
    except Exception:
        logger.warning(
            "Redis blacklist check failed for jti=%s; failing open "
            "(request allowed).",
            jti,
            exc_info=True,
        )
        return False
