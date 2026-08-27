import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.modules.auth.repository import AuthRepository
from app.modules.sessions.model import Session
from app.modules.sessions.repository import SessionRepository


class SessionService:
    """Service layer for session management operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = SessionRepository(db)
        self.auth_repo = AuthRepository(db)

    async def list_sessions(self, user_id: uuid.UUID) -> list[Session]:
        """List all active sessions for the given user."""
        return await self.repo.get_active_sessions_by_user(user_id)

    async def revoke_session(self, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
        """
        Revoke a single session belonging to the given user.

        Revokes the session's refresh token(s) too, so a stolen or lost
        device can no longer mint new access tokens via /auth/refresh.
        NOTE: any access token already issued for this session remains
        valid until its own (short) expiry — see the security note in
        Task 10 of PROGRESS.md for why this is an accepted trade-off.

        Raises:
            AppError(404): session does not exist, is already inactive,
                or does not belong to this user. Same error for all three
                cases so a caller cannot use the response to enumerate
                other users' session IDs.
        """
        session = await self.repo.get_by_id(session_id)

        if not session or session.user_id != user_id or not session.is_active:
            raise AppError(
                status_code=404,
                error_code="session_not_found",
                title="Session Not Found",
                detail="No active session with that ID was found for this account.",
            )

        await self.repo.revoke(session_id)
        await self.auth_repo.revoke_refresh_tokens_by_session(session_id)
        await self._write_audit_log(user_id=user_id, session_id=session_id)

    async def _write_audit_log(self, user_id: uuid.UUID, session_id: uuid.UUID) -> None:
        """Write an audit log entry for the session revocation."""
        from app.modules.audit.model import AuditLog

        log = AuditLog(
            user_id=user_id,
            action="session.revoke",
            description=f"Session {session_id} revoked by user",
            status="success",
        )
        self.db.add(log)
        await self.db.commit()
