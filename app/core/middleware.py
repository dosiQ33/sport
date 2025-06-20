import time
import logging
import uuid
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging_utils import error_tracker

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware для автоматического логирования HTTP запросов
    """

    def __init__(self, app: ASGIApp, exclude_paths: list = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
        ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Пропускаем служебные endpoints
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        # Генерируем уникальный ID запроса
        request_id = str(uuid.uuid4())[:8]
        start_time = time.time()

        # Добавляем request_id в request state для использования в других местах
        request.state.request_id = request_id

        # Логируем начало запроса
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "query_params": (
                    str(request.query_params) if request.query_params else None
                ),
                "client_ip": self._get_client_ip(request),
                "user_agent": request.headers.get("user-agent"),
                "content_type": request.headers.get("content-type"),
            },
        )

        try:
            # Выполняем запрос
            response = await call_next(request)

            # Вычисляем время выполнения
            duration = time.time() - start_time

            # Логируем завершение запроса
            logger.info(
                f"Request completed: {request.method} {request.url.path}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": round(duration * 1000, 2),
                    "response_size": response.headers.get("content-length"),
                },
            )

            # Добавляем request_id в response headers для трассировки
            response.headers["X-Request-ID"] = request_id

            return response

        except Exception as e:
            duration = time.time() - start_time

            # Логируем ошибку
            logger.error(
                f"Request failed: {request.method} {request.url.path}",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration * 1000, 2),
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
            )

            # Отслеживаем ошибку
            error_tracker.track_error(
                error_type=type(e).__name__,
                error_message=str(e),
                context={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration * 1000, 2),
                },
            )

            # Перебрасываем исключение для обработки error handlers
            raise

    def _get_client_ip(self, request: Request) -> str:
        """Получить IP клиента с учетом proxy"""
        # Проверяем заголовки от прокси
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            # Берем первый IP из списка
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip

        # Fallback на прямой IP
        return request.client.host if request.client else "unknown"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware для добавления security headers
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        # Добавляем security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Content Security Policy (базовый)
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self'; "
            "connect-src 'self'"
        )
        response.headers["Content-Security-Policy"] = csp

        return response


class PerformanceMonitoringMiddleware(BaseHTTPMiddleware):
    """
    Middleware для мониторинга производительности
    """

    def __init__(self, app: ASGIApp, slow_request_threshold: float = 1.0):
        super().__init__(app)
        self.slow_request_threshold = slow_request_threshold  # секунды

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start_time = time.time()

        try:
            response = await call_next(request)
            duration = time.time() - start_time

            # Логируем медленные запросы
            if duration > self.slow_request_threshold:
                logger.warning(
                    f"Slow request detected: {request.method} {request.url.path}",
                    extra={
                        "method": request.method,
                        "path": request.url.path,
                        "duration_ms": round(duration * 1000, 2),
                        "threshold_ms": self.slow_request_threshold * 1000,
                        "status_code": response.status_code,
                        "category": "performance",
                    },
                )

            return response

        except Exception as e:
            duration = time.time() - start_time

            # Логируем производительность даже для ошибочных запросов
            logger.error(
                f"Request failed with duration: {duration:.3f}s",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": round(duration * 1000, 2),
                    "error_type": type(e).__name__,
                    "category": "performance",
                },
            )

            raise


class CORSCustomMiddleware(BaseHTTPMiddleware):
    """
    Кастомный CORS middleware с логированием
    """

    def __init__(self, app: ASGIApp, allow_origins: list = None):
        super().__init__(app)
        self.allow_origins = allow_origins or ["*"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        origin = request.headers.get("origin")

        # Логируем CORS запросы
        if origin:
            logger.debug(
                f"CORS request from origin: {origin}",
                extra={
                    "origin": origin,
                    "method": request.method,
                    "path": request.url.path,
                    "category": "cors",
                },
            )

        # Обрабатываем preflight запросы
        if request.method == "OPTIONS":
            response = Response()
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, DELETE, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = "*"
            response.headers["Access-Control-Max-Age"] = "86400"
            return response

        response = await call_next(request)

        # Добавляем CORS headers
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Credentials"] = "false"

        return response


class ErrorTrackingMiddleware(BaseHTTPMiddleware):
    """
    Middleware для отслеживания ошибок на уровне HTTP
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            response = await call_next(request)

            # Отслеживаем HTTP ошибки (4xx, 5xx)
            if response.status_code >= 400:
                error_tracker.track_error(
                    error_type=f"HTTP_{response.status_code}",
                    error_message=f"HTTP {response.status_code} response",
                    context={
                        "method": request.method,
                        "path": request.url.path,
                        "status_code": response.status_code,
                        "client_ip": request.client.host if request.client else None,
                    },
                )

            return response

        except Exception as e:
            # Отслеживаем необработанные исключения
            error_tracker.track_error(
                error_type=f"UNHANDLED_{type(e).__name__}",
                error_message=str(e),
                context={
                    "method": request.method,
                    "path": request.url.path,
                    "client_ip": request.client.host if request.client else None,
                },
            )

            raise


def setup_middleware(app, config: dict = None):
    """
    Настройка всех middleware для приложения

    Args:
        app: FastAPI приложение
        config: Конфигурация middleware
    """
    config = config or {}

    # Порядок важен! Middleware применяются в обратном порядке добавления

    # 1. Error tracking (последний, чтобы отловить все ошибки)
    app.add_middleware(ErrorTrackingMiddleware)

    # 2. Performance monitoring
    app.add_middleware(
        PerformanceMonitoringMiddleware,
        slow_request_threshold=config.get("slow_request_threshold", 1.0),
    )

    # 3. Security headers
    app.add_middleware(SecurityHeadersMiddleware)

    # 4. Request logging (первый, чтобы логировать все запросы)
    app.add_middleware(
        RequestLoggingMiddleware,
        exclude_paths=config.get(
            "exclude_paths", ["/health", "/docs", "/openapi.json", "/redoc"]
        ),
    )

    logger.info("All middleware configured successfully")
