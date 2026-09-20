import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.auth.model import MFARecoveryCode, RefreshToken
from app.modules.sessions.model import Session


class AuthRepository:
    """Repository for refresh token and session operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # --- Refresh Token ------------------------------

    async def create_refresh_token(
        self,
        user_id: uuid.UUID,
        token_hash: str,
        session_id: uuid.UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> RefreshToken:
        """
        Store a hashed refresh token in the database.

        We NEVER store the raw token — only its SHA-256 hash.
        If the DB is compromised, the hashes are useless without the raw tokens.
        """
        expires_at = datetime.now(UTC) + timedelta(
            days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
        )
        token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
            is_revoked=False,
        )
        self.db.add(token)
        await self.db.commit()
        await self.db.refresh(token)
        return token

    async def get_refresh_token_by_hash(self, token_hash: str) -> RefreshToken | None:
        """
        Look up a refresh token by its hash.

        This is called on every token refresh request.
        The index on token_hash ensures this is an O(log n) operation.
        """
        result = await self.db.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == token_hash,
                RefreshToken.is_revoked.is_(False),
            )
        )
        return result.scalar_one_or_none()

    async def revoke_refresh_token(self, token_id: uuid.UUID) -> None:
        """
        Mark a refresh token as revoked.

        We mark instead of delete to preserve the audit trail.
        A deleted token cannot be investigated if suspicious activity is detected.
        """
        await self.db.execute(
            update(RefreshToken)
            .where(RefreshToken.id == token_id)
            .values(is_revoked=True, revoked_at=datetime.now(UTC))
        )
        await self.db.commit()

    async def revoke_all_user_tokens(self, user_id: uuid.UUID) -> None:
        """
        Revoke ALL active refresh tokens for a user.

        Called when:
        - Suspicious token reuse is detected (possible theft)
        - User explicitly logs out of all devices
        - Admin disables the account
        """
        await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_id,
                RefreshToken.is_revoked.is_(False),
            )
            .values(is_revoked=True, revoked_at=datetime.now(UTC))
        )
        await self.db.commit()

    async def revoke_refresh_tokens_by_session(self, session_id: uuid.UUID) -> None:
        """
        Revoke all active refresh tokens tied to a specific session.

        Used by SessionService.revoke_session() (Task 10) when a user
        signs a single device out remotely: it must kill that device's
        ability to mint new access tokens without touching the user's
        other active sessions.
        """
        await self.db.execute(
            update(RefreshToken)
            .where(
                RefreshToken.session_id == session_id,
                RefreshToken.is_revoked.is_(False),
            )
            .values(is_revoked=True, revoked_at=datetime.now(UTC))
        )
        await self.db.commit()

    # --- Sessions ------------------------------

    async def create_session(
        self,
        user_id: uuid.UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
        device_name: str | None = None,
        device_type: str | None = None,
        browser: str | None = None,
        os: str | None = None,
    ) -> Session:
        """Create a new active session for the user."""
        expires_at = datetime.now(UTC) + timedelta(
            days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
        )
        session = Session(
            user_id=user_id,
            ip_address=ip_address,
            user_agent=user_agent,
            device_name=device_name,
            device_type=device_type,
            browser=browser,
            os=os,
            last_active_at=datetime.now(UTC),
            expires_at=expires_at,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def deactivate_session(self, session_id: uuid.UUID) -> None:
        """Deactivate a specific session (logout from one device)."""
        await self.db.execute(
            update(Session)
            .where(Session.id == session_id)
            .values(is_active=False, revoked_at=datetime.now(UTC))
        )
        await self.db.commit()

    async def deactivate_all_user_sessions(self, user_id: uuid.UUID) -> None:
        """Deactivate all active sessions for a user (logout from all devices)."""
        await self.db.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.is_active.is_(True))
            .values(is_active=False, revoked_at=datetime.now(UTC))
        )
        await self.db.commit()

    # --- MFA Recovery Codes ------------------------------

    async def create_recovery_codes(
        self, user_id: uuid.UUID, code_hashes: list[str]
    ) -> None:
        """
        Persist a fresh batch of hashed MFA recovery codes.

        Called once, right after MFA is confirmed (MFAService.confirm()).
        Only the SHA-256 hashes are ever written — the raw codes are
        shown to the user exactly once, in the API response, and never
        touch the database or logs.
        """
        for code_hash in code_hashes:
            self.db.add(MFARecoveryCode(user_id=user_id, code_hash=code_hash))
        await self.db.commit()

    async def get_active_recovery_codes(
        self, user_id: uuid.UUID
    ) -> list[MFARecoveryCode]:
        """Return all unused recovery codes for a user."""
        result = await self.db.execute(
            select(MFARecoveryCode).where(
                MFARecoveryCode.user_id == user_id,
                MFARecoveryCode.is_used.is_(False),
            )
        )
        return result.scalars().all()

    async def mark_recovery_code_used(self, code_id: uuid.UUID) -> None:
        """
        Mark a single recovery code as consumed.

        Codes are marked used, never deleted — consistent with the
        refresh-token revocation pattern elsewhere in this repository —
        so a used code still shows up if this account is ever audited.
        """
        await self.db.execute(
            update(MFARecoveryCode)
            .where(MFARecoveryCode.id == code_id)
            .values(is_used=True, used_at=datetime.now(UTC))
        )
        await self.db.commit()

    async def invalidate_recovery_codes(self, user_id: uuid.UUID) -> None:
        """
        Mark every outstanding recovery code for a user as used.

        Called when MFA is disabled (MFAService.disable()): none of the
        previously issued codes should still be redeemable once MFA
        itself is off and a fresh secret would be generated on re-enrollment.
        """
        await self.db.execute(
            update(MFARecoveryCode)
            .where(
                MFARecoveryCode.user_id == user_id,
                MFARecoveryCode.is_used.is_(False),
            )
            .values(is_used=True, used_at=datetime.now(UTC))
        )
        await self.db.commit()
