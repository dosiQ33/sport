"""
Centralized exception handlers for FastAPI
"""

import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from tenacity import RetryError

from .exceptions import (
    AppException,
    BusinessLogicError,
    ResourceNotFoundError,
    AuthenticationError,
    AuthorizationError,
    ValidationError,
    DatabaseError,
    ExternalServiceError,
    RateLimitError,
    TelegramAuthError,
)

logger = logging.getLogger(__name__)


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handler for all application-specific exceptions"""
    logger.error(
        f"Application error: {exc.error_code}",
        extra={
            "error_code": exc.error_code,
            "message": exc.message,
            "details": exc.details,
            "path": str(request.url),
            "method": request.method,
        },
    )

    # Map exception types to HTTP status codes
    status_mapping = {
        BusinessLogicError: status.HTTP_400_BAD_REQUEST,
        ResourceNotFoundError: status.HTTP_404_NOT_FOUND,
        AuthenticationError: status.HTTP_401_UNAUTHORIZED,
        AuthorizationError: status.HTTP_403_FORBIDDEN,
        ValidationError: status.HTTP_422_UNPROCESSABLE_ENTITY,
        DatabaseError: status.HTTP_500_INTERNAL_SERVER_ERROR,
        ExternalServiceError: status.HTTP_502_BAD_GATEWAY,
        RateLimitError: status.HTTP_429_TOO_MANY_REQUESTS,
        TelegramAuthError: status.HTTP_401_UNAUTHORIZED,
    }

    status_code = status_mapping.get(type(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)

    response_data = {
        "error": exc.error_code,
        "message": exc.message,
    }

    # Include details for non-production environments or specific error types
    if exc.details and isinstance(exc, (ValidationError, BusinessLogicError)):
        response_data["details"] = exc.details

    return JSONResponse(status_code=status_code, content=response_data)


async def sqlalchemy_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    """Handler for SQLAlchemy database errors"""
    logger.error(
        f"Database error: {type(exc).__name__}",
        extra={
            "error_type": type(exc).__name__,
            "error_msg": str(exc),
            "path": str(request.url),
            "method": request.method,
        },
    )

    # Handle specific SQLAlchemy errors
    if isinstance(exc, IntegrityError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "error": "INTEGRITY_ERROR",
                "message": "Data integrity constraint violation",
            },
        )
    elif isinstance(exc, OperationalError):
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": "DATABASE_UNAVAILABLE",
                "message": "Database service is temporarily unavailable",
            },
        )
    else:
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "DATABASE_ERROR",
                "message": "An unexpected database error occurred",
            },
        )


async def retry_exception_handler(request: Request, exc: RetryError) -> JSONResponse:
    """Handler for retry exhaustion errors"""
    logger.error(
        f"Retry exhausted: {exc}",
        extra={
            "path": str(request.url),
            "method": request.method,
            "last_attempt": str(exc.last_attempt) if exc.last_attempt else None,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "SERVICE_UNAVAILABLE",
            "message": "Service is temporarily unavailable, please try again later",
        },
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handler for all unhandled exceptions"""
    logger.error(
        f"Unhandled exception: {type(exc).__name__}",
        extra={
            "error_type": type(exc).__name__,
            "error_msg": str(exc),
            "path": str(request.url),
            "method": request.method,
        },
        exc_info=True,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"error": "INTERNAL_ERROR", "message": "An unexpected error occurred"},
    )


def register_exception_handlers(app):
    """Register all exception handlers with FastAPI app"""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_exception_handler)
    app.add_exception_handler(RetryError, retry_exception_handler)
    app.add_exception_handler(Exception, general_exception_handler)
