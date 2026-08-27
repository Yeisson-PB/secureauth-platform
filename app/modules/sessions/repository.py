import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sessions.model import Session


class SessionRepository:
    """Repository for session-related database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_active_sessions_by_user(self, user_id: uuid.UUID) -> list[Session]:
        """
        Return all active sessions for a user, most recently active first.

        Sessions without a recorded last_active_at (shouldn't normally
        happen, but defensively handled) sort after ones that do.
        """
        result = await self.db.execute(
            select(Session)
            .where(Session.user_id == user_id, Session.is_active.is_(True))
            .order_by(
                Session.last_active_at.desc().nulls_last(),
                Session.created_at.desc(),
            )
        )
        return list(result.scalars().all())

    async def get_by_id(self, session_id: uuid.UUID) -> Session | None:
        """Fetch a single session by ID, regardless of owner or status."""
        result = await self.db.execute(select(Session).where(Session.id == session_id))
        return result.scalar_one_or_none()

    async def revoke(self, session_id: uuid.UUID) -> None:
        """Mark a session inactive. Does not touch associated refresh tokens —
        callers needing that should also call
        AuthRepository.revoke_refresh_tokens_by_session()."""
        await self.db.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(is_active=False, revoked_at=datetime.now(UTC))
        )
        await self.db.commit()
