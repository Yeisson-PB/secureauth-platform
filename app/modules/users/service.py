from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.core.security import hash_password
from app.modules.users.model import User
from app.modules.users.repository import UserRepository
from app.modules.users.schemas import (
    PasswordChangeRequest,
    UserRegisterRequest,
    UserUpdateRequest,
)


class UserService:
    """Service layer for user-related operations."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = UserRepository(db)

    async def register(
        self,
        data: UserRegisterRequest,
        ip_address: str | None = None,
    ) -> User:
        """Register a new user account."""
        if await self.repo.get_by_email(data.email):
            raise AppError(
                status_code=409,
                error_code="email_already_registered",
                title="Email Already Registered",
                detail=(
                    "An account with this email address already exists. "
                    "Please use a different email or sign in."
                ),
            )
        hashed_password = hash_password(data.password)
        user = await self.repo.create(
            email=data.email,
            hashed_password=hashed_password,
            full_name=data.full_name,
        )
        await self._write_audit_log(
            db=self.db,
            user=user,
            action="user.register",
            description=f"New account registered for {user.email}",
            ip_address=ip_address,
            status="success",
        )
        return user

    async def get_profile(self, user_id) -> User:
        """Get user profile by ID."""
        user = await self.repo.get_by_id(user_id)
        if not user:
            raise AppError(
                status_code=404,
                error_code="user_not_found",
                title="User Not Found",
                detail="The requested user account does not exist.",
            )
        if not user.is_active:
            raise AppError(
                status_code=403,
                error_code="account_disabled",
                title="Account Disabled",
                detail="This user account is currently disabled. Please contact support.",
            )
        return user

    async def update_profile(
        self,
        user_id,
        data: UserUpdateRequest,
    ) -> User:
        """Update user profile information."""
        user = await self.get_profile(user_id)
        updated = await self.repo.update_profile(
            user_id=user.id,
            full_name=data.full_name,
        )
        return updated

    async def change_password(
        self,
        user_id,
        data: PasswordChangeRequest,
        ip_address: str | None = None,
    ) -> None:
        """Change user password."""
        from app.core.security import verify_password

        user = await self.get_profile(user_id)

        # Verify current password
        if not user.hashed_password or not verify_password(
            data.current_password, user.hashed_password
        ):
            raise AppError(
                status_code=400,
                error_code="invalid_current_password",
                title="Invalid Current Password",
                detail="The current password you entered is incorrect.",
            )

        # Hash and update the new password
        new_hash = hash_password(data.new_password)
        await self.repo.update_password(user.id, new_hash)
        await self._write_audit_log(
            db=self.db,
            user=user,
            action="user.password_changed",
            description="User changed their password",
            ip_address=ip_address,
            status="success",
        )

    @staticmethod
    async def _write_audit_log(
        db: AsyncSession,
        user: User,
        action: str,
        description: str,
        ip_address: str | None,
        status: str = "success",
        metadata: dict | None = None,
    ) -> None:
        """Write an audit log entry for user actions."""
        from app.modules.audit.model import AuditLog

        log = AuditLog(
            user_id=user.id,
            actor_email=user.email,
            action=action,
            description=description,
            ip_address=ip_address,
            status=status,
            context=metadata,
        )
        db.add(log)
        await db.commit()
