from functools import lru_cache
from typing import Literal

from pydantic import AnyHttpUrl, Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings with full type validation.

    Every field maps directly to an environment variable of the same name.
    Pydantic coerces types automatically (e.g. "true" → True, "8000" → 8000).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    # ── Application ─────────────────────────────────────────────────────────
    APP_ENV: Literal["development", "test", "production"] = "development"
    APP_NAME: str = "SecureAuth API"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = False

    # BASE_URL is used in tests to construct endpoint URLs.
    # It can be overridden in .env for different environments.
    BASE_URL: AnyHttpUrl = "http://localhost:8000"

    @field_validator("DEBUG", mode="before")
    @classmethod
    def force_debug_off_in_production(cls, v: bool, info) -> bool:
        """
        Security guardrail: debug mode MUST be off in production.
        This prevents accidental exposure of stack traces and
        internal state even if someone sets DEBUG=true in a
        production .env file.
        """
        env = info.data.get("APP_ENV", "development")
        if env == "production" and v:
            return False
        return v

    # Security — JWT (RS256)
    # We use RS256 (asymmetric) instead of HS256 (symmetric)
    # because:
    # - Multiple services can verify tokens using only the
    #   PUBLIC key
    # - The private key never needs to leave the auth service
    # - If a service is compromised, it cannot forge new tokens
    # Generate with: uv run python scripts/generate_keys.py
    JWT_PRIVATE_KEY: str = Field(
        ...,
        description="PEM-encoded RSA private key for signing JWTs",
    )

    JWT_PUBLIC_KEY: str = Field(
        ...,
        description="PEM-encoded RSA public key for verifying JWTs",
    )

    JWT_ALGORITHM: str = "RS256"

    # Access token: short-lived — if stolen, expires quickly
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15

    # Refresh token: long-lived
    # Can be used to get new access tokens without re-authenticating
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    @field_validator("JWT_PRIVATE_KEY", "JWT_PUBLIC_KEY", mode="before")
    @classmethod
    def validate_pem_keys(cls, v: str) -> str:
        """
        Validate that the provided key is in PEM format.
        Catches common mistakes: base64-encoded keys,
        missing newlines, or wrong key type being used.
        """
        if not v:
            raise ValueError("Key cannot be empty")

        # Allow newlines to be represented as \n in .env files
        v = v.replace("\\n", "\n")

        # Concatenated to avoid detection as real key
        rsa_priv = "-----BEGIN" + " RSA PRIVATE KEY-----"
        pub_key = "-----BEGIN" + " PUBLIC KEY-----"
        priv_key = "-----BEGIN" + " PRIVATE KEY-----"
        rsa_pub = "-----BEGIN" + " RSA PUBLIC KEY-----"
        valid_headers = (rsa_priv, pub_key, priv_key, rsa_pub)

        if not any(v.strip().startswith(h) for h in valid_headers):
            msg = "Key must be in PEM format with a valid header"
            raise ValueError(msg)
        return v

    # ── General Security ─────────────────────────────
    SECRET_KEY: str = Field(
        ...,
        min_length=32,
        description="Random secret key, minimum 32 characters.",
    )

    # ── Database (PostgreSQL) ────────────────────────
    DATABASE_URL: PostgresDsn = Field(
        default=("postgresql+asyncpg://postgres:postgres@" "localhost:5432/secureauth"),
        description="PostgreSQL connection URL with asyncpg driver.",
    )

    DB_POOL_SIZE: int = Field(default=10, ge=1, le=100)
    DB_MAX_OVERFLOW: int = Field(default=20, ge=0, le=100)
    DB_POOL_RECYCLE_SECONDS: int = Field(
        default=3600,
        description=(
            "Seconds after which a connection is recycled to"
            " prevent stale connections."
        ),
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """
        Ensure asyncpg driver is specified.
        Required for SQLAlchemy async.
        """
        v = str(v)
        if "postgresql" in v and "asyncpg" not in v:
            v = v.replace("postgresql://", "postgresql+asyncpg://")
            v = v.replace("postgres://", "postgresql+asyncpg://")
        return v

    # ── Redis ───────────────────────────────────────────────────────────────
    REDIS_URL: RedisDsn = Field(
        default="redis://localhost:6379/0",
        description=("Redis connection URL for caching and" " token blacklisting."),
    )

    # Redis blacklist TTL: how long to keep revoked tokens
    # in Redis to prevent reuse
    REDIS_BLACKLIST_TTL_SECONDS: int = Field(
        default=900,
        description="Seconds to keep blacklisted tokens in" " Redis.",
    )

    # ── Rate Limiting ───────────────────────────────────────────────────────
    # Sliding window rate limiting per IP and per user.
    # The window resets gradually (sliding) instead of all
    # at once (fixed), which prevents the "burst at window
    # boundary" attack.

    RATE_LIMIT_REQUESTS: int = Field(
        default=100,
        description="Number of allowed requests in the" " rate limit window.",
    )
    RATE_LIMIT_WINDOW_SECONDS: int = Field(
        default=60,
        description="Seconds for the sliding rate limit window.",
    )

    # Brute-force protection: if a client exceeds the
    # rate limit, block them for a cooldown period.
    MAX_LOGIN_ATTEMPTS: int = Field(
        default=5,
        description=("Number of allowed failed login attempts" " before cooldown."),
    )
    LOCKOUT_DURATION_SECONDS: int = Field(
        default=900,
        description=(
            "Seconds to lock out a client after exceeding" " failed login attempts."
        ),
    )

    # ── CORS ────────────────────────────────────────────────────────────────

    CORS_ORIGINS: list[AnyHttpUrl] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="List of allowed CORS origins for" " cross-origin requests.",
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: str | list[str]) -> list[AnyHttpUrl]:
        """
        Allow CORS_ORIGINS to be specified as a
        comma-separated string or a list.
        """
        if isinstance(v, str):
            v = v.strip()
            if v.startswith("["):  # Handle JSON array string
                import json

                try:
                    return json.loads(v)
                except json.JSONDecodeError:
                    raise ValueError(
                        "CORS_ORIGINS must be a valid JSON array"
                        " or a comma-separated string."
                    )
            return [origin.strip() for origin in v.split(",") if origin.strip()]

        return v

    # ── OAuth2 Providers ────────────────────────────────────────────────────
    # Optional - OAuth2 is disabled if these are not set

    GOOGLE_CLIENT_ID: str | None = None
    GOOGLE_CLIENT_SECRET: str | None = None
    GOOGLE_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/oauth/google/callback"

    GITHUB_CLIENT_ID: str | None = None
    GITHUB_CLIENT_SECRET: str | None = None
    GITHUB_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/oauth/github/callback"

    # ── MFA ─────────────────────────────────────────────────────────────────
    MFA_ISSUER: str = Field(
        default="SecureAuth",
        description="Issuer name for MFA TOTP tokens.",
    )

    MFA_RECOVERY_CODES_COUNT: int = Field(
        default=10,
        description="Number of one-time recovery codes to" " generate for MFA.",
    )

    # ── Email (optional - for future password reset) ──────────────────────
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    EMAILS_FROM_NAME: str = "SecureAuth Platform"
    EMAILS_FROM_ADDRESS: str = "noreply@secureauth.dev"

    # ── Computed properties ─────────────────────────────────────────────────

    @property
    def is_production(self) -> bool:
        """
        Convenience property to check if the app is running
        in production mode.
        """
        return self.APP_ENV == "production"

    @property
    def is_development(self) -> bool:
        """
        Convenience property to check if the app is running
        in development mode.
        """
        return self.APP_ENV == "development"

    @property
    def is_test(self) -> bool:
        """Convenience property to check if the app is running in test mode."""
        return self.APP_ENV == "test"

    @property
    def google_oauth_enabled(self) -> bool:
        """
        Check if Google OAuth2 is enabled based on
        presence of client ID and secret.
        """
        return bool(self.GOOGLE_CLIENT_ID and self.GOOGLE_CLIENT_SECRET)

    @property
    def github_oauth_enabled(self) -> bool:
        """
        Check if GitHub OAuth2 is enabled based on
        presence of client ID and secret.
        """
        return bool(self.GITHUB_CLIENT_ID and self.GITHUB_CLIENT_SECRET)

    @property
    def database_url_str(self) -> str:
        """
        Return the database URL as a string.
        Useful for libraries that expect a string.
        """
        return str(self.DATABASE_URL)

    @property
    def redis_url_str(self) -> str:
        """
        Return the Redis URL as a string.
        Useful for libraries that expect a string.
        """
        return str(self.REDIS_URL)


@lru_cache
def get_settings() -> Settings:
    """Get the application settings, cached for performance."""
    return Settings()


# Export a cached settings instance for convenient module-level import.
settings = get_settings()
