from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

# Engine for asynchronous database connection
engine = create_async_engine(
    settings.database_url_str,
    echo=settings.DEBUG,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_recycle=settings.DB_POOL_RECYCLE_SECONDS,
    pool_pre_ping=True,
)

# Session maker for creating asynchronous sessions
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


#  FastAPI dependency to get an asynchronous database session
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an asynchronous database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def create_tables() -> None:
    """Create database tables based on the defined models."""
    import app.modules.audit.model
    import app.modules.auth.model
    import app.modules.sessions.model
    import app.modules.users.model  # noqa: F401
    from app.shared.base_model import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_tables() -> None:
    """Drop all database tables."""
    import app.modules.audit.model
    import app.modules.auth.model
    import app.modules.sessions.model
    import app.modules.users.model  # noqa: F401
    from app.shared.base_model import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
