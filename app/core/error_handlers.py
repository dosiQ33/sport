"""
Централизованные обработчики ошибок для FastAPI
"""

import logging
import traceback
from typing import Union
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import ValidationException
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import (
    SQLAlchemyError,
    IntegrityError,
    OperationalError,
    TimeoutError,
    DisconnectionError,
)
from asyncpg.exceptions import (
    PostgresError,
    ConnectionFailureError,
    ConnectionDoesNotExistError,
    TooManyConnectionsError,
)

from app.core.exceptions import (
    BaseAppException,
    DatabaseError,
    DatabaseConnectionError,
    DatabaseTimeoutError,
    DatabaseIntegrityError,
    ValidationError as AppValidationError,
)

logger = logging.getLogger(__name__)


async def app_exception_handler(
    request: Request, exc: BaseAppException
) -> JSONResponse:
    """Обработчик пользовательских исключений приложения"""

    # Логируем ошибку
    log_level = logging.WARNING if exc.status_code < 500 else logging.ERROR
    logger.log(
        log_level,
        f"App exception: {exc.error_code} - {exc.message}",
        extra={
            "error_code": exc.error_code,
            "status_code": exc.status_code,
            "details": exc.details,
            "path": request.url.path,
            "method": request.method,
        },
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "details": exc.details,
            "path": request.url.path,
        },
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Обработчик стандартных HTTP исключений"""

    logger.warning(
        f"HTTP exception: {exc.status_code} - {exc.detail}",
        extra={
            "status_code": exc.status_code,
            "path": request.url.path,
            "method": request.method,
        },
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": "HTTP_ERROR",
            "message": exc.detail,
            "details": {},
            "path": request.url.path,
        },
    )


async def validation_exception_handler(
    request: Request, exc: Union[ValidationException, PydanticValidationError]
) -> JSONResponse:
    """Обработчик ошибок валидации"""

    if isinstance(exc, PydanticValidationError):
        errors = exc.errors()
    else:
        errors = exc.errors() if hasattr(exc, "errors") else [{"msg": str(exc)}]

    # Форматируем ошибки валидации
    formatted_errors = []
    for error in errors:
        location = " -> ".join(str(loc) for loc in error.get("loc", []))

        # FIXED: Handle non-serializable input safely
        input_value = error.get("input")
        safe_input = None

        if input_value is not None:
            try:
                # Try to serialize to test if it's JSON-safe
                import json

                json.dumps(input_value)
                safe_input = input_value
            except (TypeError, ValueError):
                # If not JSON-serializable, convert to string representation
                safe_input = str(input_value)

        formatted_errors.append(
            {
                "field": location,
                "message": error.get("msg", "Validation error"),
                "type": error.get("type", "value_error"),
                "input": safe_input,  # Now safe for JSON serialization
            }
        )

    logger.warning(
        f"Validation error: {len(formatted_errors)} field(s)",
        extra={
            "errors": formatted_errors,
            "path": request.url.path,
            "method": request.method,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "VALIDATION_ERROR",
            "message": f"Validation failed for {len(formatted_errors)} field(s)",
            "details": {"fields": formatted_errors},
            "path": request.url.path,
        },
    )


async def database_exception_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    """Обработчик ошибок SQLAlchemy"""

    # Определяем тип ошибки и создаем соответствующее исключение
    if isinstance(exc, IntegrityError):
        # Парсим constraint name из сообщения
        constraint = "unknown"
        if exc.orig and hasattr(exc.orig, "constraint_name"):
            constraint = exc.orig.constraint_name
        elif "constraint" in str(exc.orig).lower():
            # Простой парсинг constraint name из сообщения
            import re

            match = re.search(r'constraint "([^"]+)"', str(exc.orig))
            if match:
                constraint = match.group(1)

        app_exc = DatabaseIntegrityError(constraint, {"original_error": str(exc.orig)})

    elif isinstance(exc, (OperationalError, DisconnectionError)):
        app_exc = DatabaseConnectionError("Database connection lost")

    elif isinstance(exc, TimeoutError):
        app_exc = DatabaseTimeoutError("database_operation", 30)

    else:
        app_exc = DatabaseError(f"Database operation failed: {str(exc)}")

    # Логируем детали ошибки
    logger.error(
        f"Database exception: {type(exc).__name__} - {str(exc)}",
        extra={
            "exception_type": type(exc).__name__,
            "path": request.url.path,
            "method": request.method,
            "traceback": traceback.format_exc(),
        },
    )

    return await app_exception_handler(request, app_exc)


async def postgres_exception_handler(
    request: Request, exc: PostgresError
) -> JSONResponse:
    """Обработчик ошибок PostgreSQL/asyncpg"""

    if isinstance(exc, (ConnectionFailureError, ConnectionDoesNotExistError)):
        app_exc = DatabaseConnectionError("PostgreSQL connection failed")
    elif isinstance(exc, TooManyConnectionsError):
        app_exc = DatabaseConnectionError("Too many database connections")
    else:
        # Парсим PostgreSQL error code
        error_code = getattr(exc, "sqlstate", "unknown")
        app_exc = DatabaseError(
            f"PostgreSQL error: {str(exc)}", details={"postgres_code": error_code}
        )

    logger.error(
        f"PostgreSQL exception: {type(exc).__name__} - {str(exc)}",
        extra={
            "exception_type": type(exc).__name__,
            "postgres_code": getattr(exc, "sqlstate", None),
            "path": request.url.path,
            "method": request.method,
        },
    )

    return await app_exception_handler(request, app_exc)


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Обработчик всех остальных исключений"""

    logger.error(
        f"Unhandled exception: {type(exc).__name__} - {str(exc)}",
        extra={
            "exception_type": type(exc).__name__,
            "path": request.url.path,
            "method": request.method,
            "traceback": traceback.format_exc(),
        },
    )

    # В production не показываем детали ошибки
    import os

    is_development = os.getenv("ENVIRONMENT", "production").lower() in [
        "development",
        "dev",
    ]

    if is_development:
        details = {
            "exception_type": type(exc).__name__,
            "traceback": traceback.format_exc(),
        }
    else:
        details = {}

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred",
            "details": details,
            "path": request.url.path,
        },
    )


def setup_exception_handlers(app):
    """Регистрация всех обработчиков исключений"""

    # Пользовательские исключения приложения
    app.add_exception_handler(BaseAppException, app_exception_handler)

    # Стандартные HTTP исключения
    app.add_exception_handler(HTTPException, http_exception_handler)

    # Ошибки валидации
    app.add_exception_handler(ValidationException, validation_exception_handler)
    app.add_exception_handler(PydanticValidationError, validation_exception_handler)

    # Ошибки базы данных
    app.add_exception_handler(SQLAlchemyError, database_exception_handler)
    app.add_exception_handler(PostgresError, postgres_exception_handler)

    # Общий обработчик
    app.add_exception_handler(Exception, general_exception_handler)

    logger.info("Exception handlers registered successfully")
