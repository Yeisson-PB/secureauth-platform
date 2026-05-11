from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application settings
    APP_ENV: str = "development"
    DEBUG: bool = False
    SECRET_KEY: str = "changeme-in-production"

    # CORS settings
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:8000",
    ]

    # DATABASE settings
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/secureauth"
    )

    # Redis settings
    REDIS_URL: str = "redis://localhost:6379/0"


settings = Settings()
