"""Plataforma SecureAuth: punto de entrada principal de la aplicación."""

from contextlib import asynccontextmanager

# CRITICAL: Import all models early to register them with SQLAlchemy
# before any relationships are resolved
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import models early to register them with SQLAlchemy without binding the
# package name `app` in this module's namespace (avoids redefinition of
# `app` below).
import app.modules  # noqa: F401
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import configure_exception_handlers
from app.core.redis_client import close_redis_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    On shutdown, closes the shared Redis connection pool cleanly instead
    of leaking connections. The pool itself is created lazily on first
    use (see app.core.redis_client.get_redis_pool), so there is nothing
    to do on startup.
    """
    yield
    await close_redis_pool()


app = FastAPI(  # noqa: F811
    title="SecureAuth API",
    description="API para la plataforma de autenticación segura.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# CORS Middleware para permitir solicitudes desde el frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de los manejadores de excepciones
configure_exception_handlers(app)

# Incluir las rutas de la API
app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["Health"])
async def health_check() -> dict:
    """Endpoint de salud para verificar que la aplicación está funcionando."""
    return {"status": "ok", "version": "0.1.0"}
