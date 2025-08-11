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

from app.staff.routers import users as staff_users
from app.staff.routers import clubs as staff_clubs
from app.staff.routers import sections as staff_sections
from app.staff.routers import groups as staff_groups
from app.staff.routers import superadmin
from app.staff.routers import invitations
from app.staff.routers import team as staff_team
from app.students.routers import users as student_users
from app.staff.routers import schedule

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
    description="Tensu.kz",
    version=APP_VERSION,
    lifespan=lifespan,
    debug=DEBUG,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://training-tracker-mini-app.vercel.app",
        "https://tensu-students.vercel.app",
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

setup_exception_handlers(app)

setup_middleware(
    app,
    {
        "slow_request_threshold": 5.0,
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
app.include_router(staff_groups.router, prefix="/api/v1")
app.include_router(invitations.router, prefix="/api/v1")
app.include_router(student_users.router, prefix="/api/v1")
app.include_router(superadmin.router, prefix="/api/v1")
app.include_router(staff_team.router, prefix="/api/v1")
app.include_router(schedule.router, prefix="/api/v1")
