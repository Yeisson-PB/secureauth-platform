import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.shared.base_model import Base, UUIDMixin

if TYPE_CHECKING:
    from app.modules.users.model import User


class AuditLog(Base, UUIDMixin):
    """Model for audit logs."""

    __tablename__ = "audit_logs"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    actor_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Human-readable description for display in admin UI
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Network context
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True
    )  # Supports IPv4 and IPv6
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, default="success"
    )  # e.g., "success", "failure"
    context: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )  # Additional structured data

    # Table configuration
    __table_args__ = (
        Index("idx_audit_logs_user_id_created_at", "user_id", "created_at"),
        Index("idx_audit_logs_action_created_at", "action", "created_at"),
    )

    # Relationships
    user: Mapped["User | None"] = relationship(
        "User", back_populates="audit_logs"
    )  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"<AuditLog(id={self.id}, action='{self.action}', user_id={self.user_id}, "
            f"status={self.status})>"
        )
