import logging

import redis.asyncio as aioredis
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import AppError
from app.modules.auth.service import AuthService
from app.modules.users.model import User
from app.modules.users.repository import UserRepository

logger = logging.getLogger(__name__)

# HTTPBearer extracts the token from the Authorization: Bearer <token> header
# auto_error=False: we handle the 401 ourselves for better error messages
bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency: extracts and validates the JWT from the request.

    Steps:
    1. Extract Bearer token from Authorization header
    2. Decode and verify JWT signature + expiry (RS256)
    3. Check token is not blacklisted in Redis
    4. Load user from DB and verify account is active

    Usage:
        current_user: User = Depends(get_current_user)

    Raises:
        AppError(401): missing token, invalid token, blacklisted, user not found
        AppError(403): account disabled
    """
    # --- Step 1: Extract token ------------------
    if not credentials:
        raise AppError(
            status_code=401,
            error_code="missing_token",
            title="Authentication Required",
            detail="Please provide a valid Bearer token in the Authorization header.",
        )

    token = credentials.credentials

    # --- Step 2: Decode JWT ---------------------
    payload = AuthService.decode_access_token(token)
    user_id = payload.get("sub")
    jti = payload.get("jti")

    if not user_id or not jti:
        raise AppError(
            status_code=401,
            error_code="invalid_token",
            title="Invalid Token",
            detail="The token payload is malformed.",
        )

    # --- Step 3: Check Redis blacklist ------------
    # This is what makes logout instant — even though the JWT hasn't expired,
    # if its jti is in the blacklist, we reject it.
    try:
        r = aioredis.from_url(settings.redis_url_str)
        is_blacklisted = await r.exists(f"blacklist:{jti}")
        await r.aclose()

        if is_blacklisted:
            raise AppError(
                status_code=401,
                error_code="token_revoked",
                title="Token Revoked",
                detail="This token has been revoked. Please log in again.",
            )
    except AppError:
        raise
    except Exception as exc:
        # If Redis is down, we can't check the blacklist.
        # Depending on your security posture, you might want to FAIL CLOSED
        # (reject all requests when Redis is down) or FAIL OPEN
        # (allow requests but log the Redis failure).
        # We FAIL OPEN here for availability — change to raise in high-security envs.
        logger.warning(
            "Redis blacklist check failed; allowing request.",
            exc_info=exc,
        )

    # --- Step 4: Load user from DB ----------------
    import uuid

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(uuid.UUID(user_id))

    if not user:
        raise AppError(
            status_code=401,
            error_code="user_not_found",
            title="User Not Found",
            detail="The user associated with this token no longer exist.",
        )

    if not user.is_active:
        raise AppError(
            status_code=403,
            error_code="account_disabled",
            title="Account Disabled",
            detail="This account has been disabled.",
        )

    return user


async def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:
    """
    Dependency for admin-only endpoints.
    Extends get_current_user with superuser check.

    Usage:
        current_user: User = Depends(get_current_superuser)
    """
    if not current_user.is_superuser:
        raise AppError(
            status_code=403,
            error_code="insufficient_permissions",
            title="Insufficient Permissions",
            detail="This endpoint requires administrator privileges.",
        )
    return current_user
