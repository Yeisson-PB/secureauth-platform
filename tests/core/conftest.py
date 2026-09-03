"""Test fixtures scoped to tests/core/."""

import pytest

from app.core import redis_client


@pytest.fixture(autouse=True)
async def reset_redis_pool():
    """
    Force a fresh Redis connection pool AND a clean rate-limit keyspace
    for every test function.

    Two separate problems, two separate fixes bundled here:

    1. Connection lifecycle: app.core.redis_client keeps a single
       module-level connection pool (_redis_pool). Under pytest-asyncio's
       function-scoped event loops, reusing that pool across tests means
       test N tries to use a connection created under test N-1's
       (now-closed) loop → "Event loop is closed" errors that
       check_rate_limit silently swallows via fail-open. Closing the
       pool before/after each test forces a fresh, working connection.

    2. Data isolation: this is REAL Redis, not a mock — counters written
       by one test persist and leak into the next. Every middleware test
       hits the same key (ratelimit:ip:127.0.0.1, the ASGI test client's
       default IP), so without cleanup, later tests inherit hit counts
       from earlier ones and assert against the wrong `remaining` value.
       Flushing ratelimit:* keys before each test guarantees every test
       starts from a clean counter, regardless of run order.
    """
    await redis_client.close_redis_pool()
    client = redis_client.get_redis_client()
    async for key in client.scan_iter(match="ratelimit:*"):
        await client.delete(key)

    yield

    await redis_client.close_redis_pool()
