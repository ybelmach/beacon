from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from beacon.core.exceptions import AppError
from beacon.core.logging import get_logger
from beacon.core.problem_details import create_problem_response, slug_for_status, title_for_status

logger = get_logger(__name__)


async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle FastAPI request validation errors in RFC 9457 format."""
    errors = exc.errors()
    error_details = [
        {
            "field": " -> ".join(str(loc) for loc in error.get("loc", [])),
            "message": error.get("msg"),
            "type": error.get("type"),
        }
        for error in errors
    ]

    detail = "Request validation failed"
    if len(errors) == 1:
        detail = f"Validation error: {errors[0].get('msg', 'Invalid input')}"

    logger.warning(
        "validation_error",
        path=request.url.path,
        fields=[{"field": error["field"], "type": error["type"]} for error in error_details],
    )

    return create_problem_response(
        request,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=detail,
        slug="validation-error",
        extensions={"errors": error_details},
    )


async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Handle HTTP exceptions raised outside the domain hierarchy in RFC 9457 format."""
    detail = exc.detail or title_for_status(exc.status_code)

    logger.warning(
        "http_exception",
        path=request.url.path,
        status_code=exc.status_code,
        detail=detail,
    )

    return create_problem_response(
        request,
        status_code=exc.status_code,
        detail=detail,
        slug=slug_for_status(exc.status_code),
        headers=exc.headers,
    )


async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
    """Map domain errors to RFC 9457 responses using the mapping each class declares."""
    logger.warning(
        "domain_exception",
        exception_type=type(exc).__name__,
        detail=exc.detail,
        path=request.url.path,
        status_code=exc.status_code,
    )

    return create_problem_response(
        request,
        status_code=exc.status_code,
        detail=exc.detail,
        slug=exc.slug,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Single place to wire up every exception handler; called once from create_app()."""
    app.add_exception_handler(RequestValidationError, handle_validation_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)  # type: ignore[arg-type]
    app.add_exception_handler(AppError, handle_app_error)  # type: ignore[arg-type]
