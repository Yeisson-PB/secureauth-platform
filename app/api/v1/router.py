from fastapi import APIRouter

api_router = APIRouter()


@api_router.get("/ping", tags=["Health Check"])
async def ping() -> dict:
    """
    Health check endpoint to verify that the API is running.
    """
    return {"message": "pong", "api_version": "v1"}
