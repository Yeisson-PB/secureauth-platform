from fastapi import APIRouter

from app.modules.auth.router import router as auth_router
from app.modules.users.router import router as users_router

api_router = APIRouter()


# Health check endpoint
@api_router.get("/ping", tags=["Health Check"])
async def ping() -> dict:
    """
    Health check endpoint to verify that the API is running.
    """
    return {"message": "pong", "api_version": "v1"}


# Domain modules
api_router.include_router(users_router)
api_router.include_router(auth_router)
