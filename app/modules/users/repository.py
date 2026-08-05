import uuid
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.users.model import User


class UserRepository:
    """Repository for user-related database operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Fetch a user by their ID."""
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a user by their email."""
        result = await self.db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        """Check if an email is already registered."""
        result = await self.db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none() is not None

    async def create(
        self,
        email: str,
        full_name: str,
        hashed_password: str | None = None,
        oauth_provider: str | None = None,
        oauth_provider_id: str | None = None,
        is_verified: bool = False,
    ) -> User:
        """Create a new user."""
        user = User(
            email=email.lower(),
            full_name=full_name,
            hashed_password=hashed_password,
            oauth_provider=oauth_provider,
            oauth_provider_id=oauth_provider_id,
            is_verified=is_verified,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_profile(
        self,
        user_id: uuid.UUID,
        full_name: str,
    ) -> User:
        """Update user profile information."""
        user = await self.get_by_id(user_id)
        if not user:
            return None

        if full_name is not None:
            user.full_name = full_name

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_password(
        self,
        user_id: uuid.UUID,
        hashed_password: str,
    ) -> None:
        """Update user hashed password."""
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(hashed_password=hashed_password)
        )
        await self.db.commit()

    async def increment_failed_login_attempts(self, user_id: uuid.UUID) -> int:
        """Increment failed login attempts for a user."""
        user = await self.get_by_id(user_id)
        if not user:
            return 0
        user.failed_login_attempts += 1
        await self.db.commit()
        return user.failed_login_attempts

    async def increment_failed_attempts(self, user_id: uuid.UUID) -> int:
        """Backward-compatible alias used by the auth service."""
        return await self.increment_failed_login_attempts(user_id)

    async def reset_failed_attempts(self, user_id: uuid.UUID) -> None:
        """Reset failed login attempts for a user."""
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(failed_login_attempts=0, locked_until=None)
        )
        await self.db.commit()

    async def lock_user(self, user_id: uuid.UUID, locked_until: datetime) -> None:
        """Lock a user account until a specified time."""
        await self.db.execute(
            update(User).where(User.id == user_id).values(locked_until=locked_until)
        )
        await self.db.commit()

    async def update_last_login(
        self,
        user_id: uuid.UUID,
        ip_address: str | None = None,
    ) -> None:
        """Record the timestamp and IP of the last successful login."""
        from datetime import UTC

        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(
                last_login_at=datetime.now(UTC),
                last_login_ip=ip_address,
                failed_login_attempts=0,
                locked_until=None,
            )
        )
        await self.db.commit()

    async def set_mfa_secret(
        self,
        user_id: uuid.UUID,
        secret: str,
    ) -> None:
        """Set the MFA secret for a user."""
        await self.db.execute(
            update(User).where(User.id == user_id).values(mfa_secret=secret)
        )
        await self.db.commit()

    async def enable_mfa(self, user_id: uuid.UUID) -> None:
        """Enable MFA for a user."""
        await self.db.execute(
            update(User).where(User.id == user_id).values(mfa_enabled=True)
        )
        await self.db.commit()

    async def disable_mfa(self, user_id: uuid.UUID) -> None:
        """Disable MFA for a user."""
        await self.db.execute(
            update(User)
            .where(User.id == user_id)
            .values(mfa_enabled=False, mfa_secret=None)
        )
        await self.db.commit()

    async def deactivate(self, user_id: uuid.UUID) -> None:
        """Deactivate a user account."""
        await self.db.execute(
            update(User).where(User.id == user_id).values(is_active=False)
        )
        await self.db.commit()
