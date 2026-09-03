from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from app.core.rate_limit_middleware import RateLimitMiddleware


async def _ping(request):
    return PlainTextResponse("ok")


def _build_app(limit: int, window_seconds: int) -> Starlette:
    app = Starlette(routes=[Route("/ping", _ping)])
    app.add_middleware(
        RateLimitMiddleware, limit=limit, window_seconds=window_seconds, enabled=True
    )
    return app


class TestRateLimitMiddleware:
    async def test_requests_under_limit_pass_through(self):
        app = _build_app(limit=3, window_seconds=60)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(3):
                response = await client.get("/ping")
                assert response.status_code == 200

    async def test_request_over_limit_returns_429(self):
        app = _build_app(limit=2, window_seconds=60)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.get("/ping")
            await client.get("/ping")

            response = await client.get("/ping")

            assert response.status_code == 429
            data = response.json()
            assert data["error_code"] == "rate_limit_exceeded"
            assert response.headers["Retry-After"] == "60"

    async def test_rate_limit_headers_present_on_success(self):
        app = _build_app(limit=5, window_seconds=60)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/ping")

            assert response.headers["X-RateLimit-Limit"] == "5"
            assert response.headers["X-RateLimit-Remaining"] == "4"

    async def test_different_ips_have_independent_limits(self):
        app = _build_app(limit=1, window_seconds=60)
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp_a = await client.get("/ping", headers={"X-Forwarded-For": "10.0.0.1"})
            resp_b = await client.get("/ping", headers={"X-Forwarded-For": "10.0.0.2"})

            assert resp_a.status_code == 200
            assert resp_b.status_code == 200

    async def test_exempt_paths_are_never_limited(self):
        app = Starlette(routes=[Route("/health", _ping)])
        app.add_middleware(
            RateLimitMiddleware, limit=1, window_seconds=60, enabled=True
        )
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(5):
                response = await client.get("/health")
                assert response.status_code == 200

    async def test_disabled_middleware_never_limits(self):
        """
        Simulates the test-environment default (enabled=False): even a
        limit of 1 must never trigger a 429 while disabled.
        """
        app = Starlette(routes=[Route("/ping", _ping)])
        app.add_middleware(
            RateLimitMiddleware, limit=1, window_seconds=60, enabled=False
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            for _ in range(5):
                response = await client.get("/ping")
                assert response.status_code == 200
