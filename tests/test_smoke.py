"""
Smoke tests — verify the application starts and core config loads.
These run in every CI pipeline regardless of feature completeness.
"""


def test_app_imports() -> None:
    """Verify the FastAPI app can be imported without errors."""
    from app.main import app

    assert app is not None


def test_app_title() -> None:
    """Verify the app has the correct title."""
    from app.main import app

    assert app.title == "SecureAuth Platform"


def test_settings_load() -> None:
    """Verify Pydantic settings load from environment."""
    from app.core.config import settings

    assert settings is not None
    assert settings.app_env == "test"


def test_health_endpoint(client) -> None:  # type: ignore[no-untyped-def]
    """Verify /health returns 200."""
    pass  # Will be implemented with fixtures in Task 8
