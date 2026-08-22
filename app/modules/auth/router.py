from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.schemas import LoginRequest, RefreshTokenRequest, TokenResponse
from app.modules.auth.service import AuthService
from app.modules.users.model import User
from app.modules.users.schemas import UserResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_client_ip(request: Request) -> str | None:
    """Extract real client IP (checks X-Forwarded-For first)."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Login with email and password",
    description=(
        "Authenticate with email and password. "
        "Returns an RS256-signed JWT access token (15 min) "
        "and a refresh token (30 days). "
        "Use the access token in the Authorization: Bearer header."
    ),
    responses={
        200: {"description": "Login successful — token pair returned"},
        401: {"description": "Invalid credentials"},
        403: {"description": "Account disabled or locked"},
    },
)
async def login(
    request: Request,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Authenticate user and issue JWT + refresh token."""
    service = AuthService(db)
    return await service.login(
        email=data.email,
        password=data.password,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Rotate token pair",
    description=(
        "Exchange a valid refresh token for a new access + refresh token pair. "
        "The old refresh token is immediately invalidated (rotation). "
        "If the token has already been used, all sessions are revoked."
    ),
    responses={
        200: {"description": "New token pair issued"},
        401: {"description": "Invalid or expired refresh token"},
    },
)
async def refresh_tokens(
    request: Request,
    data: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Rotate the token pair using a valid refresh token."""
    service = AuthService(db)
    return await service.refresh_tokens(
        refresh_token=data.refresh_token,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Logout from current session",
    description=(
        "Invalidate the current access token and refresh token. "
        "The access token is blacklisted in Redis immediately. "
        "The refresh token is revoked in the database."
    ),
    responses={
        200: {"description": "Logged out successfully"},
        401: {"description": "Not authenticated"},
    },
)
async def logout(
    request: Request,
    data: RefreshTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Logout from the current session."""
    # Extract the raw Authorization header to get the jti
    auth_header = request.headers.get("Authorization", "")
    access_token = auth_header.replace("Bearer ", "").strip()

    # Decode to get the jti (don't re-verify — already done by get_current_user)
    import jwt as pyjwt

    payload = pyjwt.decode(
        access_token,
        settings.JWT_PUBLIC_KEY,
        algorithms=[settings.JWT_ALGORITHM],
    )

    service = AuthService(db)
    await service.logout(
        user_id=current_user.id,
        access_token_jti=payload.get("jti"),
        refresh_token=data.refresh_token,
    )
    return {"message": "Logged out successfully"}


@router.post(
    "/logout-all",
    status_code=status.HTTP_200_OK,
    summary="Logout from all devices",
    description="Revoke all refresh tokens and sessions for the current user.",
    responses={
        200: {"description": "Logged out from all devices"},
        401: {"description": "Not authenticated"},
    },
)
async def logout_all(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Logout from all devices."""
    service = AuthService(db)
    await service.logout_all(user_id=current_user.id)
    return {"message": "Logged out from all devices"}


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
    description="Returns the profile of the authenticated user. Requires Bearer token.",
    responses={
        200: {"description": "User profile"},
        401: {"description": "Not authenticated"},
    },
)
async def get_me(
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    """
    Get the current authenticated user's profile.

    This endpoint demonstrates how get_current_user works:
    - Extract JWT from Authorization header
    - Verify signature + expiry
    - Check Redis blacklist
    - Load user from DB
    - Return user to route handler
    """
    return UserResponse.model_validate(current_user)
