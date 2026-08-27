from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class SessionResponse(BaseModel):
    """A single active session, as shown to the owning user."""

    id: UUID
    device_name: str | None = Field(
        None, description="Human-readable device label, e.g. 'Chrome on macOS'."
    )
    device_type: str | None = Field(
        None, description="'desktop', 'mobile', 'tablet', or 'unknown'."
    )
    browser: str | None = None
    os: str | None = None
    ip_address: str | None = None
    is_current: bool = Field(
        ..., description="True if this is the session the request itself used."
    )
    last_active_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
