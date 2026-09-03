import asyncio
import uuid

from app.core.rate_limiter import check_rate_limit
from app.core.redis_client import get_redis_client


def _unique_key() -> str:
    return f"test_rate_limiter:{uuid.uuid4().hex}"


class TestCheckRateLimit:
    async def test_allows_requests_under_limit(self):
        key = _unique_key()
        try:
            for expected_remaining in (4, 3, 2, 1, 0):
                result = await check_rate_limit(key, limit=5, window_seconds=60)
                assert result.allowed is True
                assert result.remaining == expected_remaining
        finally:
            await get_redis_client().delete(key)

    async def test_blocks_requests_over_limit(self):
        key = _unique_key()
        try:
            for _ in range(3):
                result = await check_rate_limit(key, limit=3, window_seconds=60)
                assert result.allowed is True

            blocked = await check_rate_limit(key, limit=3, window_seconds=60)
            assert blocked.allowed is False
            assert blocked.remaining == 0
        finally:
            await get_redis_client().delete(key)

    async def test_separate_keys_have_independent_limits(self):
        key_a = _unique_key()
        key_b = _unique_key()
        try:
            for _ in range(2):
                await check_rate_limit(key_a, limit=2, window_seconds=60)

            blocked_a = await check_rate_limit(key_a, limit=2, window_seconds=60)
            assert blocked_a.allowed is False

            # key_b has never been touched — it must still be fully available
            allowed_b = await check_rate_limit(key_b, limit=2, window_seconds=60)
            assert allowed_b.allowed is True
        finally:
            await get_redis_client().delete(key_a)
            await get_redis_client().delete(key_b)

    async def test_resets_after_window(self):
        key = _unique_key()
        try:
            first = await check_rate_limit(key, limit=1, window_seconds=1)
            assert first.allowed is True

            second = await check_rate_limit(key, limit=1, window_seconds=1)
            assert second.allowed is False

            await asyncio.sleep(1.2)

            third = await check_rate_limit(key, limit=1, window_seconds=1)
            assert third.allowed is True
        finally:
            await get_redis_client().delete(key)

    async def test_fails_open_when_redis_unreachable(self, monkeypatch):
        def _broken_client():
            raise ConnectionError("simulated Redis outage")

        monkeypatch.setattr("app.core.rate_limiter.get_redis_client", _broken_client)

        result = await check_rate_limit(_unique_key(), limit=1, window_seconds=60)
        assert result.allowed is True
