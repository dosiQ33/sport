from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from slowapi.errors import RateLimitExceeded

from app.core.limits import limiter, rate_limit_handler
from app.core.init_db import init_database
from app.core.error_handlers import setup_exception_handlers
from app.core.database import db_manager
from app.core.middleware import setup_middleware
from app.core.logging_utils import (
    setup_logging,
    get_logger,
    log_business_event,
    error_tracker,
)
from app.core.config import (
    validate_config,
    APP_NAME,
    APP_VERSION,
    DEBUG,
    LOG_LEVEL,
    LOG_FORMAT,
)

# Импортируем исключения в начале, так как они используются в debug endpoints
from app.core.exceptions import (
    NotFoundError,
    BusinessLogicError,
    DatabaseError,
    ValidationError,
)
from app.staff.routers import users as staff_users
from app.staff.routers import clubs as staff_clubs
from app.staff.routers import sections as staff_sections
from app.staff.routers import groups as staff_groups
from app.staff.routers import superadmin
from app.staff.routers import invitations
from app.staff.routers import team as staff_team
from app.students.routers import users as student_users

# Настройка системы логирования
setup_logging(LOG_LEVEL, LOG_FORMAT)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""

    # Startup
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")

    try:
        # Валидация конфигурации
        validate_config()
        logger.info("✅ Configuration validated")

        # Проверка соединения с БД
        await db_manager.check_connection()
        logger.info("✅ Database connection established")

        # Инициализация базы данных
        await init_database()
        logger.info("✅ Database initialized")

        # Логируем бизнес-событие
        log_business_event(
            "application_started",
            "system",
            0,
            {
                "version": APP_VERSION,
                "environment": "development" if DEBUG else "production",
            },
        )

        logger.info("🚀 Application startup completed")

    except Exception as e:
        logger.error(f"❌ Application startup failed: {str(e)}")
        # Отслеживаем критическую ошибку
        error_tracker.track_error(
            "STARTUP_ERROR",
            str(e),
            {"component": "application_startup", "version": APP_VERSION},
        )
        raise

    yield

    # Shutdown
    logger.info("🛑 Shutting down application...")

    try:
        await db_manager.close_connections()
        logger.info("✅ Database connections closed")

    except Exception as e:
        logger.error(f"❌ Error during shutdown: {str(e)}")

    logger.info("👋 Application shutdown completed")


app = FastAPI(
    title=APP_NAME,
    description="A CRUD API with Telegram Web App authentication, centralized error handling, and comprehensive logging",
    version=APP_VERSION,
    lifespan=lifespan,
    debug=DEBUG,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://training-tracker-mini-app.vercel.app",
        "https://web.telegram.org",
        "https://k.web.telegram.org",
        "https://z.web.telegram.org",
        "https://a.web.telegram.org",
        "http://localhost:3000",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Настройка обработчиков ошибок (до добавления middleware и роутеров)
setup_exception_handlers(app)

# Настройка middleware
setup_middleware(
    app,
    {
        "slow_request_threshold": 2.0,  # Логировать запросы медленнее 2 секунд
        "exclude_paths": [
            "/health",
            "/docs",
            "/openapi.json",
            "/redoc",
            "/favicon.ico",
        ],
    },
)

# Add rate limiter to app state
app.state.limiter = limiter

# Add rate limit exception handler
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# Include routers with API version prefix
app.include_router(staff_users.router, prefix="/api/v1")
app.include_router(staff_clubs.router, prefix="/api/v1")
app.include_router(staff_sections.router, prefix="/api/v1")
app.include_router(staff_groups.router, prefix="/api/v1")  # ← НОВЫЙ РОУТЕР
app.include_router(invitations.router, prefix="/api/v1")
app.include_router(student_users.router, prefix="/api/v1")
app.include_router(superadmin.router, prefix="/api/v1")
app.include_router(staff_team.router, prefix="/api/v1")


@app.get("/")
async def root():
    """Welcome endpoint"""
    return {
        "message": f"{APP_NAME} API",
        "version": APP_VERSION,
        "environment": "development" if DEBUG else "production",
        "docs": "/docs",
        "health": "/health",
        "ssl": "enabled",
        "features": [
            "Centralized error handling",
            "Database retry mechanism",
            "Rate limiting",
            "Telegram authentication",
            "Team management",
            "Groups management",  # ← НОВАЯ ФИЧА
        ],
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint with comprehensive system status
    """
    try:
        # Проверяем соединение с базой данных
        await db_manager.check_connection()
        db_status = "healthy"
        db_details = "Connection successful"
    except Exception as e:
        logger.error(f"Health check database error: {str(e)}")
        db_status = "unhealthy"
        db_details = "Connection failed"

    # Получаем статистику ошибок
    error_stats = error_tracker.get_stats()

    # Определяем общий статус
    overall_status = "healthy"
    if db_status != "healthy":
        overall_status = "unhealthy"
    elif error_stats["total_errors"] > 100:  # Много ошибок
        overall_status = "degraded"

    health_data = {
        "status": overall_status,
        "service": APP_NAME.lower().replace(" ", "-"),
        "version": APP_VERSION,
        "environment": "development" if DEBUG else "production",
        "timestamp": "2025-06-19T12:00:00Z",  # Можно заменить на datetime.now()
        "checks": {
            "database": {"status": db_status, "details": db_details},
            "error_tracking": {
                "status": "healthy" if error_stats["total_errors"] < 100 else "warning",
                "total_errors": error_stats["total_errors"],
                "unique_error_types": error_stats["unique_error_types"],
            },
        },
        "ssl": "enabled",
    }

    # Логируем health check
    logger.debug(
        "Health check performed",
        extra={
            "overall_status": overall_status,
            "db_status": db_status,
            "total_errors": error_stats["total_errors"],
        },
    )

    return health_data


@app.get("/metrics")
async def get_metrics():
    """
    Metrics endpoint for monitoring systems
    """
    error_stats = error_tracker.get_stats()

    return {
        "application": {
            "name": APP_NAME,
            "version": APP_VERSION,
            "environment": "development" if DEBUG else "production",
        },
        "errors": error_stats,
        "system": {
            "uptime_info": "Available in future versions",
            "memory_usage": "Available in future versions",
        },
    }


@app.get("/debug/errors")
async def get_error_details():
    """
    Detailed error information (only in debug mode)
    """
    if not DEBUG:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("endpoint", "This endpoint is only available in debug mode")

    error_stats = error_tracker.get_stats()

    return {
        "error_tracking": error_stats,
        "recent_errors": error_stats.get("last_errors", []),
        "environment": "development",
        "warning": "This endpoint exposes sensitive information and is only available in development mode",
    }


@app.get("/debug/test-error")
async def test_error_handling():
    """Тестовый endpoint для проверки обработки ошибок (только в dev)"""
    if not DEBUG:
        raise NotFoundError("endpoint", "This endpoint is only available in debug mode")

    # Тестируем разные типы ошибок
    import random

    error_type = random.choice(
        ["app_exception", "database_error", "validation_error", "unexpected_error"]
    )

    logger.info(f"Testing error type: {error_type}")

    if error_type == "app_exception":
        raise BusinessLogicError(
            "This is a test business logic error",
            {"test_data": "sample_value", "error_category": "testing"},
        )

    elif error_type == "database_error":
        raise DatabaseError(
            "This is a test database error",
            {"operation": "test_operation", "table": "test_table"},
        )

    elif error_type == "validation_error":
        raise ValidationError(
            "This is a test validation error",
            {"field": "test_field", "value": "invalid_value"},
        )

    else:
        raise Exception("This is a test unexpected error for testing purposes")


@app.post("/debug/reset-error-stats")
async def reset_error_statistics():
    """
    Сбросить статистику ошибок (только в debug режиме)
    """
    if not DEBUG:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("endpoint", "This endpoint is only available in debug mode")

    old_stats = error_tracker.get_stats()
    error_tracker.reset_stats()

    logger.info(
        "Error statistics reset",
        extra={
            "previous_total_errors": old_stats["total_errors"],
            "previous_unique_types": old_stats["unique_error_types"],
        },
    )

    return {
        "message": "Error statistics reset successfully",
        "previous_stats": {
            "total_errors": old_stats["total_errors"],
            "unique_error_types": old_stats["unique_error_types"],
        },
        "current_stats": error_tracker.get_stats(),
    }
