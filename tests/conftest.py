# Use test database URL
from urllib.parse import urlsplit, urlunsplit

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import get_db
from app.main import app
from app.shared.base_model import Base

parsed_database_url = urlsplit(str(settings.DATABASE_URL))
current_db_name = parsed_database_url.path.lstrip("/")
if current_db_name.endswith("_test"):
    test_db_name = current_db_name
else:
    test_db_name = f"{current_db_name}_test"

TEST_DATABASE_URL = urlunsplit(
    (
        parsed_database_url.scheme,
        parsed_database_url.netloc,
        f"/{test_db_name}",
        parsed_database_url.query,
        parsed_database_url.fragment,
    )
)

# Create a separate async engine for tests
test_engine = create_async_engine(TEST_DATABASE_URL, echo=False, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


@pytest.fixture(scope="session", autouse=True)
async def setup_test_db():
    """Create the test database schema before tests and drop it after."""

    import app.modules.audit.model  # noqa: F401
    import app.modules.auth.model  # noqa: F401
    import app.modules.sessions.model  # noqa: F401
    import app.modules.users.model  # noqa: F401

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield

    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
async def clean_db():
    """Clean the database before each test."""
    yield
    # After each test: truncate all tables in reverse FK order

    async with test_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


@pytest.fixture
async def client() -> AsyncClient:
    # Each request gets its own fresh session from the app's override
    async def override_get_db():
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
