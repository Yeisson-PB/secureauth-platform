from pydantic import BaseModel, EmailStr, Field

# --- Request Schemas -------------------------------


class LoginRequest(BaseModel):
    """Credentials for email/password authentication."""

    email: EmailStr = Field(..., examples=["user@example.com"])
    password: str = Field(..., min_length=1, examples=["MyP@ssw0rd!"])


class RefreshTokenRequest(BaseModel):
    """Refresh token for rotating the token pair."""

    refresh_token: str = Field(..., description="The refresh token received at login")


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
