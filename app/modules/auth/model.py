from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from app.modules.session.model import Session  # noqa: F401
    from app.modules.user.model import User  # noqa: F401


class RefreshToken(Base, TimestampMixin, UUIDMixin):
    """Model for storing refresh tokens."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The token hash is stored instead of the raw token for security reasons
    token_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )

    # Session this token belongs to (for device-based revocation)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sessions.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Optional metadata for auditing and security purposes
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True
    )  # Supports IPv4 and IPv6
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Token expiration time for automatic cleanup and security
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    is_revoked: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User", back_populates="refresh_tokens"
    )  # noqa: F821
    session: Mapped["Session | None"] = relationship(  # noqa: F821
        "Session", back_populates="refresh_tokens"
    )

    def __repr__(self) -> str:
        return f"<RefreshToken id={self.id} user_id={self.user_id} revoked={self.is_revoked}>"


class MFARecoveryCode(Base, TimestampMixin, UUIDMixin):
    """Model for storing MFA recovery codes."""

    __tablename__ = "mfa_recovery_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    is_used: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User", back_populates="mfa_recovery_codes"
    )  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<MFARecoveryCode id={self.id} user_id={self.user_id} used={self.is_used}>"
        )
