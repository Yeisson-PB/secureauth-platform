import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator


# Input Schemas (Request)
class UserRegisterRequest(BaseModel):
    """Schema for user registration request."""

    email: EmailStr = Field(
        ...,
        description="User's email address. Will be stored in lowercase.",
        examples=["user@example.com"],
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description=(
            "User's password. Must be at least 8 characters long and "
            "include uppercase, lowercase, number, and special character."
        ),
        examples=["P@ssw0rd!"],
    )
    password_confirm: str = Field(
        ...,
        description="Password confirmation. Must match the password.",
        examples=["P@ssw0rd!"],
    )
    full_name: str | None = Field(
        None,
        max_length=255,
        description="User's full name.",
        examples=["John Doe"],
    )

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        """Normalize email by stripping whitespace and converting to lowercase."""
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        """Validate password strength."""
        errors = []

        if not re.search(r"[A-Z]", v):
            errors.append("at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            errors.append("at least one lowercase letter")
        if not re.search(r"\d", v):
            errors.append("at least one number")
        # include common special characters; avoid escaping quotes inside the pattern
        if not re.search(r'[!@#$%^&*(),.?:"{}|<>]', v):
            errors.append("at least one special character")

        if errors:
            raise ValueError(f"Password must contain {', '.join(errors)}.")
        return v

    @model_validator(mode="after")
    def passwords_must_match(self) -> "UserRegisterRequest":
        """Ensure that password and confirm_password match."""
        if self.password != self.password_confirm:
            raise ValueError("Password and confirm password do not match.")
        return self


class UserUpdateRequest(BaseModel):
    """Schema for user update request."""

    full_name: str = Field(
        max_length=255,
        examples=["John Doe"],
    )


class PasswordChangeRequest(BaseModel):
    """Schema for password change request."""

    current_password: str = Field(
        ...,
        min_length=1,
    )
    new_password: str = Field(
        ...,
        min_length=8,
        max_length=128,
    )
    new_password_confirm: str = Field(...)

    @field_validator("new_password")
    @classmethod
    def validate_new_password_strength(cls, v: str) -> str:
        """Validate new password strength."""
        errors = []

        if not re.search(r"[A-Z]", v):
            errors.append("at least one uppercase letter")
        if not re.search(r"[a-z]", v):
            errors.append("at least one lowercase letter")
        if not re.search(r"\d", v):
            errors.append("at least one number")
        # include common special characters; avoid escaping quotes inside the pattern
        if not re.search(r'[!@#$%^&*(),.?:"{}|<>]', v):
            errors.append("at least one special character")

        if errors:
            raise ValueError(f"Password must contain {', '.join(errors)}.")
        return v

    @model_validator(mode="after")
    def new_passwords_must_match(self) -> "PasswordChangeRequest":
        """Ensure that new_password and new_password_confirm match."""
        if self.new_password != self.new_password_confirm:
            raise ValueError("New passwords do not match")
        return self


# Output Schemas (Response)
class UserResponse(BaseModel):
    """Schema for user response."""

    id: UUID
    email: str
    full_name: str | None
    is_active: bool
    is_verified: bool
    mfa_enabled: bool
    oauth_provider: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class UserPublicResponse(BaseModel):
    """Schema for public user response (without sensitive info)."""

    id: UUID
    email: str
    full_name: str | None

    model_config = {"from_attributes": True}
