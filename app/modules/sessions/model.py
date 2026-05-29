import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import Base, TimestampMixin, UUIDMixin


class Session(Base, TimestampMixin, UUIDMixin):
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(100), nullable=True)
    os: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Raw User-Agent for logging and debugging purposes
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Network information
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True
    )  # Supports IPv6

    # Session State
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, index=True
    )

    # Timestamps for session lifecycle management
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="sessions")  # noqa: F821
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(  # noqa: F821
        "RefreshToken", back_populates="session", lazy="select"
    )

    # Table configuration
    from sqlalchemy import Index

    __table_args__ = (Index("ix_sessions_user_id_is_active", "user_id", "is_active"),)

    def __repr__(self) -> str:
        return (
            f"<Session id={self.id} user_id={self.user_id} "
            f"device={self.device_name} active={self.is_active}>"
        )
