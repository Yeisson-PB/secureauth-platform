from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Un modelo de respuesta genérico para datos paginados."""

    items: list[T]
    total: int
    next_cursor: str | None = None
    has_more: bool = False


class MessageResponse(BaseModel):
    """Un modelo de respuesta genérico para mensajes simples."""

    message: str
