from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.users.schemas import (
    PasswordChangeRequest,
    UserRegisterRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.modules.users.service import UserService

router = APIRouter(prefix="/users", tags=["Users"])


def get_client_ip(request: Request) -> str | None:
    """Extract the client's IP address from the request headers."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # The X-Forwarded-For header can contain multiple IPs, take the first one
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
    description=(
        "Create a new user account with email and password. "
        "The password is hashed with bcrypt (12 rounds) before storage. "
        "The plaintext password is never persisted."
    ),
    responses={
        201: {"description": "User registered successfully"},
        409: {"description": "Email already registered"},
        422: {"description": "Validation error"},
    },
)
async def register(
    request: Request,
    data: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Register a new user account."""
    service = UserService(db)
    ip = get_client_ip(request)
    user = await service.register(data, ip_address=ip)
    return UserResponse.model_validate(user)


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user information",
    description="Returns the profile of the currently authenticated user.",
    responses={
        200: {"description": "User profile returned"},
        401: {"description": "Not authenticated"},
    },
)
async def get_my_profile(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Get the profile of the currently authenticated user."""

    from app.core.exceptions import AppError

    raise AppError(
        status_code=501,
        error_code="not_implemented",
        title="Not Implemented",
        detail="Authentication middleware will be added in Task 8.",
    )


@router.patch(
    "/me",
    response_model=UserResponse,
    summary="Update current user information",
    description="Update the profile of the currently authenticated user.",
)
async def update_my_profile(
    request: Request,
    data: UserUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Update the profile of the currently authenticated user."""

    from app.core.exceptions import AppError

    raise AppError(
        status_code=501,
        error_code="not_implemented",
        title="Not Implemented",
        detail="Authentication middleware will be added in Task 8.",
    )


@router.post(
    "/me/change-password",
    status_code=status.HTTP_200_OK,
    summary="Change current user's password",
    description=(
        "Change the password of the currently authenticated user. "
        "Requires the current password for verification. "
    ),
)
async def change_password(
    request: Request,
    data: PasswordChangeRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Change the password of the currently authenticated user."""

    from app.core.exceptions import AppError

    raise AppError(
        status_code=501,
        error_code="not_implemented",
        title="Not Implemented",
        detail="Authentication middleware will be added in Task 8.",
    )
