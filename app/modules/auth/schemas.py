from pydantic import BaseModel, EmailStr, Field, model_validator

# --- Request Schemas -------------------------------


class LoginRequest(BaseModel):
    """Credentials for email/password authentication."""

    email: EmailStr = Field(..., examples=["user@example.com"])
    password: str = Field(..., min_length=1, examples=["MyP@ssw0rd!"])


class RefreshTokenRequest(BaseModel):
    """Refresh token for rotating the token pair."""

    refresh_token: str = Field(..., description="The refresh token received at login")


class MFAEnableConfirmRequest(BaseModel):
    """Confirms MFA enrollment by proving control of the authenticator app."""

    totp_code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="Current 6-digit TOTP code from the authenticator app.",
        examples=["123456"],
    )


class MFAVerifyRequest(BaseModel):
    """
    Second step of login for accounts with MFA enabled.

    Exactly one of totp_code or recovery_code must be provided — never
    both, and never neither. Recovery codes are the documented fallback
    for a lost authenticator device.
    """

    mfa_token: str = Field(
        ..., description="The temporary mfa_token returned by POST /auth/login"
    )
    totp_code: str | None = Field(
        None,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="Current 6-digit TOTP code.",
        examples=["123456"],
    )
    recovery_code: str | None = Field(
        None,
        min_length=8,
        description="An unused MFA recovery code, used instead of a TOTP code.",
        examples=["7K9XJ-4RTQZ"],
    )

    @model_validator(mode="after")
    def exactly_one_code_provided(self) -> "MFAVerifyRequest":
        """Require exactly one of totp_code / recovery_code — not both, not neither."""
        if bool(self.totp_code) == bool(self.recovery_code):
            raise ValueError("Provide exactly one of totp_code or recovery_code.")
        return self


class MFADisableRequest(BaseModel):
    """
    Disables MFA. Requires BOTH the current password and a valid TOTP
    code — an authenticated session alone is not enough, so a hijacked
    access token can never be used to turn off the second factor.
    """

    password: str = Field(..., min_length=1, description="Current account password.")
    totp_code: str = Field(
        ...,
        min_length=6,
        max_length=6,
        pattern=r"^\d{6}$",
        description="Current 6-digit TOTP code.",
        examples=["123456"],
    )


# --- Response Schemas -------------------------------


class TokenResponse(BaseModel):
    """
    Token pair returned after successful login or token refresh.

    access_token: short-lived JWT (RS256). Send in Authorization header.
    refresh_token: long-lived opaque token. Send to /auth/refresh to rotate.
    token_type: always "bearer" per OAuth2 spec.
    expires_in: access token lifetime in seconds (for client-side expiry tracking).
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(
        ...,
        description="Access token lifetime in seconds",
        examples=[900],
    )


class MFARequiredResponse(BaseModel):
    """
    Returned by POST /auth/login instead of TokenResponse when the
    account has MFA enabled: the password was correct, but a second
    factor is still required via POST /auth/mfa/verify.
    """

    mfa_required: bool = True
    mfa_token: str = Field(
        ...,
        description=(
            "Single-use, short-lived token to submit to POST /auth/mfa/verify "
            "along with a TOTP or recovery code. It is NOT a valid access token."
        ),
    )
    expires_in: int = Field(
        ...,
        description="Seconds until the mfa_token itself expires.",
        examples=[300],
    )


class MFAEnableResponse(BaseModel):
    """
    Returned by POST /auth/mfa/enable. MFA is NOT active yet — the user
    must scan otpauth_uri (or enter secret manually) into an
    authenticator app and confirm a code via POST /auth/mfa/enable/confirm.
    """

    secret: str = Field(..., description="Base32 TOTP secret, for manual entry.")
    otpauth_uri: str = Field(
        ..., description="otpauth:// URI — render as a QR code for easy scanning."
    )
    issuer: str = Field(..., description="Issuer name shown in the authenticator app.")


class MFAEnableConfirmResponse(BaseModel):
    """
    Returned by POST /auth/mfa/enable/confirm on success. recovery_codes
    is shown exactly once — only its SHA-256 hashes are ever persisted.
    """

    message: str
    recovery_codes: list[str] = Field(
        ...,
        description=(
            "One-time MFA recovery codes. Store them somewhere safe — "
            "they will never be shown again."
        ),
    )


class TokenPayload(BaseModel):
    """
    The decoded payload of a JWT access token.

    sub: subject — the user's UUID as string
    exp: expiry timestamp (Unix epoch)
    iat: issued at timestamp (Unix epoch)
    jti: JWT ID — unique identifier for this specific token
         Used for blacklisting on logout without storing all tokens
    type: "access" or "refresh" — prevents using a refresh token as access token
    """

    sub: str  # user UUID
    exp: str  # expiry
    iat: str  # issued at
    jti: str  # JWT ID (for blacklisting)
    type: str  # "access" or "refresh"
    sid: str | None = None  # session UUID
