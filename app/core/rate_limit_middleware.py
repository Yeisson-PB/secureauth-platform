import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.core.config import settings
from app.core.exceptions import AppError
from app.core.rate_limiter import RateLimitResult, check_rate_limit

logger = logging.getLogger(__name__)

# Paths that must never be rate limited: health checks (used by Docker/
# k8s probes and monitoring) and the API documentation UI.
_EXEMPT_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


def _get_client_ip(request: Request) -> str:
    """Extract the real client IP, preferring X-Forwarded-For (set by a
    reverse proxy) over the raw ASGI connection address."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # The X-Forwarded-For header can contain multiple IPs, the first one is the client IP.
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _extract_user_id(request: Request) -> str | None:
    """
    Best-effort extraction of the authenticated user id from the
    Authorization header, without raising on missing/invalid/expired
    tokens — those cases are simply treated as "no user-level limit
    applies", the IP-level limit still does.
    """
    # Deferred import: avoids a circular import at module load time
    # (app.modules.auth.service imports app.core modules).
    from app.modules.auth.service import AuthService

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return None

    token = auth_header[len("Bearer ") :].strip()
    try:
        payload = AuthService.decode_access_token(token)
    except AppError:
        return None
    return payload.get("sub")


def _rate_limit_response(result: RateLimitResult) -> JSONResponse:
    """RFC 7807-shaped 429 response with standard rate-limit headers."""
    return JSONResponse(
        status_code=429,
        content={
            "type": "https://secureauth.dev/errors/429",
            "title": "Too Many Requests",
            "status": 429,
            "detail": ("Rate limit exceeded. Please slow down and try again shortly."),
            "error_code": "rate_limit_exceeded",
        },
        headers={
            "Retry-After": str(result.window_seconds),
            "X-RateLimit-Limit": str(result.limit),
            "X-RateLimit-Remaining": "0",
        },
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Sliding-window rate limiting middleware.

    `limit` / `window_seconds` default to the global settings
    (RATE_LIMIT_REQUESTS / RATE_LIMIT_WINDOW_SECONDS) but can be
    overridden — mainly so tests can exercise a tight, fast limit
    without waiting on the real configured window.

    `enabled` defaults to `not settings.is_test`: the sliding window
    shares a single bucket across the whole test suite (the ASGI test
    transport doesn't carry a real client IP, so every request from
    every test lands under "ratelimit:ip:unknown"), which would make
    unrelated tests fail once the suite executes more requests than the
    limit. Rate-limiting behavior itself is covered by dedicated tests
    that explicitly set enabled=True with a small limit.
    """

    def __init__(
        self,
        app,
        limit: int | None = None,
        window_seconds: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        super().__init__(app)
        self.limit = limit or settings.RATE_LIMIT_REQUESTS
        self.window_seconds = window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS
        self.enabled = (not settings.is_test) if enabled is None else enabled

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self.enabled or request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        ip = _get_client_ip(request)
        ip_result = await check_rate_limit(
            key=f"ratelimit:ip:{ip}",
            limit=self.limit,
            window_seconds=self.window_seconds,
        )
        if not ip_result.allowed:
            return _rate_limit_response(ip_result)

        header_source = ip_result

        user_id = _extract_user_id(request)
        if user_id:
            user_result = await check_rate_limit(
                key=f"ratelimit:user:{user_id}",
                limit=self.limit,
                window_seconds=self.window_seconds,
            )
            if not user_result.allowed:
                return _rate_limit_response(user_result)
            header_source = user_result

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(header_source.limit)
        response.headers["X-RateLimit-Remaining"] = str(header_source.remaining)
        return response
