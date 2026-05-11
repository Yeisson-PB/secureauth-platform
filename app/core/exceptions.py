from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


# Excepción personalizada para errores de la aplicación
class AppError(Exception):
    def __init__(
        self,
        status_code: int,
        error_code: str,
        detail: str,
        title: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail
        self.title = title or error_code
        super().__init__(detail)


# Manejador de excepciones para AppError
def _problem_detail(
    status_code: int,
    title: str,
    detail: str,
    error_code: str,
    instance: str | None = None,
) -> dict:
    payload = {
        "type": f"https://secureauth.dev/errors/{status_code}",
        "title": title,
        "status": status_code,
        "detail": detail,
        "error_code": error_code,
    }
    if instance:
        payload["instance"] = instance
    return payload


def configure_exception_handlers(app: FastAPI) -> None:
    """Configura los manejadores de excepciones para la aplicación FastAPI."""

    @app.exception_handler(AppError)
    async def app_error_handler(
        request: Request,
        exc: AppError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_problem_detail(
                status_code=exc.status_code,
                title=exc.title,
                detail=exc.detail,
                error_code=exc.error_code,
                instance=str(request.url),
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_problem_detail(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                title="Validation Error",
                detail=str(exc.errors()),
                error_code="validation_error",
                instance=str(request.url),
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(
        request: Request,
        exc: Exception,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_problem_detail(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                title="Internal Server Error",
                detail=(
                    "Se ha producido un error inesperado. "
                    "Inténtalo de nuevo más tarde."
                ),
                error_code="internal_server_error",
                instance=str(request.url),
            ),
        )
