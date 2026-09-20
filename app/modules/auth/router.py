from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.modules.auth.dependencies import get_current_user
from app.modules.auth.mfa_service import MFAService
from app.modules.auth.schemas import (
    LoginRequest,
    MFADisableRequest,
    MFAEnableConfirmRequest,
    MFAEnableConfirmResponse,
    MFAEnableResponse,
    MFARequiredResponse,
    MFAVerifyRequest,
    RefreshTokenRequest,
    TokenResponse,
)
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
    response_model=TokenResponse | MFARequiredResponse,
    status_code=status.HTTP_200_OK,
    summary="Login with email and password",
    description=(
        "Authenticate with email and password. "
        "Returns an RS256-signed JWT access token (15 min) "
        "and a refresh token (30 days). "
        "If the account has MFA enabled, returns a short-lived `mfa_token` "
        "instead — complete the login via POST /auth/mfa/verify. "
        "Use the access token in the Authorization: Bearer header."
    ),
    responses={
        200: {
            "description": "Login successful — token pair, or mfa_token if MFA is enabled"
        },
        401: {"description": "Invalid credentials"},
        403: {"description": "Account disabled or locked"},
    },
)
async def login(
    request: Request,
    data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse | MFARequiredResponse:
    """Authenticate user and issue JWT + refresh token, or an mfa_token if MFA is on."""
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


# --- MFA ------------------------------


@router.post(
    "/mfa/enable",
    response_model=MFAEnableResponse,
    status_code=status.HTTP_200_OK,
    summary="Start MFA enrollment",
    description=(
        "Generate a new TOTP secret for the authenticated user. "
        "MFA is NOT active yet — scan the returned otpauth_uri with an "
        "authenticator app (or enter `secret` manually), then confirm a "
        "generated code via POST /auth/mfa/enable/confirm to activate it."
    ),
    responses={
        200: {"description": "TOTP secret generated"},
        401: {"description": "Not authenticated"},
        409: {"description": "MFA already enabled"},
    },
)
async def enable_mfa(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MFAEnableResponse:
    """Generate a pending TOTP secret for the authenticated user."""
    service = MFAService(db)
    return await service.enable(current_user)


@router.post(
    "/mfa/enable/confirm",
    response_model=MFAEnableConfirmResponse,
    status_code=status.HTTP_200_OK,
    summary="Confirm MFA enrollment",
    description=(
        "Confirm MFA enrollment by submitting a valid TOTP code generated "
        "from the secret returned by POST /auth/mfa/enable. On success, "
        "MFA is activated and a one-time batch of recovery codes is "
        "returned — store them safely, they are never shown again."
    ),
    responses={
        200: {"description": "MFA enabled; recovery codes issued"},
        400: {"description": "MFA enrollment was not started"},
        401: {"description": "Invalid or expired TOTP code"},
        409: {"description": "MFA already enabled"},
    },
)
async def confirm_mfa(
    data: MFAEnableConfirmRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MFAEnableConfirmResponse:
    """Confirm MFA enrollment with a valid TOTP code."""
    service = MFAService(db)
    return await service.confirm(current_user, data)


@router.post(
    "/mfa/verify",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Complete login with an MFA code",
    description=(
        "Second step of login for accounts with MFA enabled. Exchange "
        "the mfa_token returned by POST /auth/login for a real "
        "access/refresh token pair by providing a valid TOTP code or an "
        "unused recovery code. The mfa_token is single-use and expires "
        "quickly — request a new one via POST /auth/login if it lapses."
    ),
    responses={
        200: {"description": "Login completed — token pair issued"},
        401: {
            "description": (
                "Invalid/expired/already-used mfa_token, or invalid "
                "TOTP/recovery code"
            )
        },
        422: {"description": "Neither or both of totp_code/recovery_code provided"},
    },
)
async def verify_mfa(
    request: Request,
    data: MFAVerifyRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """Complete the MFA login flow and issue the final token pair."""
    service = MFAService(db)
    return await service.verify(
        data,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )


@router.post(
    "/mfa/disable",
    status_code=status.HTTP_200_OK,
    summary="Disable MFA",
    description=(
        "Disable multi-factor authentication for the authenticated user. "
        "Requires BOTH the current password and a valid TOTP code — an "
        "authenticated session alone is never enough to turn off the "
        "second factor. All outstanding recovery codes are invalidated."
    ),
    responses={
        200: {"description": "MFA disabled"},
        400: {"description": "MFA is not enabled for this account"},
        401: {"description": "Invalid password or TOTP code"},
    },
)
async def disable_mfa(
    data: MFADisableRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Disable MFA for the authenticated user."""
    service = MFAService(db)
    await service.disable(current_user, data)
    return {"message": "MFA has been disabled successfully."}
