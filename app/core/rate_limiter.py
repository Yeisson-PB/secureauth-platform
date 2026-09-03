import logging
import time
import uuid
from dataclasses import dataclass

from app.core.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# KEYS[1] = the rate limit key (e.g. "ratelimit:ip:1.2.3.4")
# ARGV[1] = current unix timestamp (float, seconds)
# ARGV[2] = window size in seconds
# ARGV[3] = max requests allowed in the window
# ARGV[4] = unique member id for this request
#
# Returns {allowed (0/1), remaining_after_this_request}
_SLIDING_WINDOW_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
local count = redis.call('ZCARD', key)

if count < limit then
    redis.call('ZADD', key, now, member)
    redis.call('PEXPIRE', key, window * 1000)
    return {1, limit - count - 1}
else
    return {0, 0}
end
"""


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    limit: int
    window_seconds: int


async def check_rate_limit(
    key: str, limit: int, window_seconds: int
) -> RateLimitResult:
    """
    Check (and, if allowed, record) a request against a sliding window
    rate limit.

    SECURITY DECISION — fail-open by design:
    If Redis is unreachable, this returns allowed=True so a Redis outage
    degrades the platform's abuse protection rather than taking down the
    entire API. Same trade-off already made for the token blacklist
    (Task 9) and applied consistently here.

    Args:
        key: fully-qualified Redis key for this limit bucket, e.g.
             "ratelimit:ip:203.0.113.5" or "ratelimit:user:<uuid>".
        limit: max requests allowed within `window_seconds`.
        window_seconds: size of the sliding window, in seconds.
    """
    now = time.time()
    member = f"{now}:{uuid.uuid4().hex}"

    try:
        client = get_redis_client()
        result = await client.eval(
            _SLIDING_WINDOW_SCRIPT,
            1,
            key,
            now,
            window_seconds,
            limit,
            member,
        )
        allowed = bool(int(result[0]))
        remaining = max(int(result[1]), 0)
        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            limit=limit,
            window_seconds=window_seconds,
        )
    except Exception:
        logger.warning(
            "Rate limit check failed for key=%s; failing open (request allowed).",
            key,
            exc_info=True,
        )
        return RateLimitResult(
            allowed=True,
            remaining=limit,
            limit=limit,
            window_seconds=window_seconds,
        )
