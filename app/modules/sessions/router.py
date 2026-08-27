from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.modules.auth.dependencies import get_current_session_id, get_current_user
from app.modules.sessions.schemas import SessionResponse
from app.modules.sessions.service import SessionService
from app.modules.users.model import User
from app.shared.schemas import MessageResponse

router = APIRouter(prefix="/sessions", tags=["Sessions"])


@router.get(
    "",
    response_model=list[SessionResponse],
    summary="List active sessions",
    description=(
        "Returns every active session (device/browser) for the "
        "currently authenticated user, most recently active first. "
        "The session used to make this request is flagged as "
        "`is_current: true`."
    ),
    responses={
        200: {"description": "List of active sessions"},
        401: {"description": "Not authenticated"},
    },
)
async def list_sessions(
    current_user: User = Depends(get_current_user),
    current_session_id: UUID | None = Depends(get_current_session_id),
    db: AsyncSession = Depends(get_db),
) -> list[SessionResponse]:
    """List all active sessions for the authenticated user."""
    service = SessionService(db)
    sessions = await service.list_sessions(current_user.id)
    return [
        SessionResponse(
            id=s.id,
            device_name=s.device_name,
            device_type=s.device_type,
            browser=s.browser,
            os=s.os,
            ip_address=s.ip_address,
            is_current=(s.id == current_session_id),
            last_active_at=s.last_active_at,
            created_at=s.created_at,
        )
        for s in sessions
    ]


@router.delete(
    "/{session_id}",
    response_model=MessageResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke a session",
    description=(
        "Revoke a single active session by ID — e.g. to sign out a lost "
        "or stolen device remotely. Revokes the session's refresh token, "
        "preventing it from minting new access tokens. Any access token "
        "already issued for that session remains valid until its own "
        "(short) natural expiry."
    ),
    responses={
        200: {"description": "Session revoked"},
        401: {"description": "Not authenticated"},
        404: {"description": "Session not found or not owned by this user"},
    },
)
async def revoke_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """Revoke a specific session belonging to the authenticated user."""
    service = SessionService(db)
    await service.revoke_session(user_id=current_user.id, session_id=session_id)
    return MessageResponse(message="Session revoked successfully")
