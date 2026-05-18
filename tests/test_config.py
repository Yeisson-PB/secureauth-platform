import re

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict

from app.core.config import Settings, get_settings
from app.core.security import (
    constants_time_compare,
    generate_secure_token,
    generate_totp_secret,
    hash_password,
    hash_token_,
    verify_password,
)

# ── Minimal valid settings for tests ─────────────────────────────────────────
VALID_PRIVATE_KEY = """-----BEGIN PRIVATE KEY-----
MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7o4qne60TB3wo
fakekeyfortest1234567890abcdefghijklmnopqrstuvwxyz==
-----END PRIVATE KEY-----"""

VALID_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAu6OKp3utEwd8KA==
fakepublickeyfortest1234567890abcdefghijklmnopqrstuvwxyz==
-----END PUBLIC KEY-----"""

MINIMAL_SETTINGS = {
    "JWT_PRIVATE_KEY": VALID_PRIVATE_KEY,
    "JWT_PUBLIC_KEY": VALID_PUBLIC_KEY,
    "SECRET_KEY": "a-secret-key-that-is-at-least-32-chars-long!!",
    "DATABASE_URL": "postgresql+asyncpg://test:test@localhost:5432/test",
    "REDIS_URL": "redis://localhost:6379/0",
}


class SettingsNoEnv(Settings):
    model_config = SettingsConfigDict(
        env_file=None, case_sensitive=True, extra="ignore"
    )


class TestSettings:
    """Tests for the Settings class and get_settings function."""

    def test_valid_settings_load(self):
        """Test that valid settings can be created."""
        s = Settings(**MINIMAL_SETTINGS, APP_ENV="development")
        assert s.APP_ENV == "development"  # Default value
        assert s.DEBUG is False  # Default value
        assert s.JWT_ALGORITHM == "RS256"  # Default value

    def test_debug_forced_off_in_production(self):
        """Test that DEBUG is forced to False in production environment."""
        s = Settings(
            **{
                **MINIMAL_SETTINGS,
                "APP_ENV": "production",
                "DEBUG": True,
            }
        )
        assert s.DEBUG is False

    def test_debug_allowed_in_development(self):
        """Test that DEBUG can be True in development environment."""
        s = Settings(
            **{
                **MINIMAL_SETTINGS,
                "APP_ENV": "development",
                "DEBUG": True,
            }
        )
        assert s.DEBUG is True

    def test_missing_jwt_private_key_raises(self, monkeypatch):
        """Test that missing JWT_PRIVATE_KEY raises ValidationError."""
        monkeypatch.delenv("JWT_PRIVATE_KEY", raising=False)
        data = {k: v for k, v in MINIMAL_SETTINGS.items() if k != "JWT_PRIVATE_KEY"}
        with pytest.raises(ValidationError):
            SettingsNoEnv(**data)

    def test_invalid_pem_keys_raise(self):
        """Test that invalid PEM keys raise ValidationError."""
        data = {**MINIMAL_SETTINGS, "JWT_PRIVATE_KEY": "not-a-valid-pem"}
        with pytest.raises(ValidationError):
            Settings(**data)

    def test_secret_key_min_length(self):
        """Test that SECRET_KEY must be at least 32 characters long."""
        data = {**MINIMAL_SETTINGS, "SECRET_KEY": "tooshort"}
        with pytest.raises(ValidationError):
            Settings(**data)

    def test_cors_origins_parsed_from_json_string(self):
        """Test that CORS_ORIGINS can be parsed from a JSON string."""
        s = Settings(
            **{
                **MINIMAL_SETTINGS,
                "CORS_ORIGINS": '["http://localhost:3000", "https://app.com"]',
            }
        )
        origin_strings = [str(origin) for origin in s.CORS_ORIGINS]

        assert "http://localhost:3000/" in origin_strings
        assert "https://app.com/" in origin_strings

    def test_cors_origins_parsed_from_csv(self):
        """Test that CORS_ORIGINS can be parsed from a comma-separated
        string."""
        s = Settings(
            **{
                **MINIMAL_SETTINGS,
                "CORS_ORIGINS": "http://localhost:3000,https://app.com",
            }
        )

        assert len(s.CORS_ORIGINS) == 2

    def test_google_oauth_disabled_when_no_credentials(self):
        """Test that Google OAuth is disabled when credentials are not
        provided."""
        s = Settings(**MINIMAL_SETTINGS)
        assert s.google_oauth_enabled is False

    def test_google_oauth_enabled_with_credentials(self):
        """Test that Google OAuth is enabled when credentials are provided."""
        s = Settings(
            **{
                **MINIMAL_SETTINGS,
                "GOOGLE_CLIENT_ID": "client-id",
                "GOOGLE_CLIENT_SECRET": "client-secret",
            }
        )
        assert s.google_oauth_enabled is True

    def test_is_production_property(self):
        """Test the is_production property."""
        s = Settings(**{**MINIMAL_SETTINGS, "APP_ENV": "production"})
        assert s.is_production is True
        assert s.is_development is False

    def test_database_url_asyncpg_coercion(self):
        """Test that DATABASE_URL with asyncpg scheme is accepted."""
        s = Settings(
            **{
                **MINIMAL_SETTINGS,
                "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost/db",
            }
        )
        assert "asyncpg" in s.database_url_str

    def test_get_settings_cached(self):
        """Test that get_settings returns the same instance on multiple
        calls."""
        get_settings.cache_clear()  # Clear cache to ensure fresh instance
        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2  # Should be the same instance due to caching


class TestPasswordSecurity:
    """Tests for password hashing and verification."""

    def test_hash_password_returns_bcrypt_hash(self):
        """Test that hash_password returns a bcrypt hash."""
        hashed = hash_password("MySecurePassword123!")
        assert hashed.startswith("$2b$")  # bcrypt hash prefix

    def test_hash_password_uses_12_rounds(self):
        """Test that hash_password uses 12 rounds of bcrypt."""
        hashed = hash_password("password")
        assert "$2b$12$" in hashed  # Check for 12 rounds in the hash

    def test_verify_password_correct(self):
        """Test that verify_password returns True for correct password."""
        password = "CorrectHorseBatteryStaple!"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_wrong(self):
        """Test that verify_password returns False for incorrect password."""
        hashed = hash_password("CorrectPassword")
        assert verify_password("WrongPassword", hashed) is False

    def test_same_password_different_hashes(self):
        """Test that hashing the same password multiple times produces
        different hashes (due to salting)."""
        password = "SamePassword"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2  # Should be different due to random salt

    def test_verify_password_with_malformed_hash(self):
        """Test that verify_password returns False when given a malformed
        hash."""
        assert verify_password("password", "not-a-valid-hash") is False


class TestTokenSecurity:
    """Tests for token generation and time comparison."""

    def test_generate_secure_token_length(self):
        """Test that generate_secure_token returns a string of the expected
        length."""
        token = generate_secure_token(32)
        assert (
            len(token) >= 40
        )  # Base64 encoding of 32 bytes should be at least 44 chars
        # but we can allow for some variation

    def test_generate_secure_token_unique(self):
        """Test that multiple calls to generate_secure_token produce unique
        tokens."""
        tokens = {generate_secure_token() for _ in range(100)}
        assert len(tokens) == 100  # All tokens should be unique

    def test_hash_token_deterministic(self):
        """Test that hash_token_ produces the same hash for the same input."""
        token = "MySecureToken123!"
        assert hash_token_(token) == hash_token_(token)

    def test_hash_token_different_inputs(self):
        """Test that hash_token_ produces different hashes for different
        inputs."""
        assert hash_token_("TokenOne") != hash_token_("TokenTwo")

    def test_constants_time_compare_equal(self):
        """Test that constants_time_compare returns True for equal strings."""
        assert constants_time_compare("SecureToken", "SecureToken") is True

    def test_constants_time_compare_not_equal(self):
        """Test that constants_time_compare returns False for different
        strings."""
        assert constants_time_compare("SecureToken", "InsecureToken") is False

    def test_generate_totp_secret_format(self):
        """Test that generate_totp_secret returns a valid base32 string."""
        secret = generate_totp_secret()
        assert re.match(
            r"^[A-Z2-7]+=*$", secret
        )  # Base32 secrets are typically 16 characters
        # long and use A-Z and 2-7
        assert len(secret) >= 32
