import logging
from fastapi import FastAPI
from contextlib import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from fastapi.middleware.cors import CORSMiddleware

from app.core.limits import limiter, rate_limit_handler
from app.core.init_db import init_database
from app.core.exception_handlers import register_exception_handlers
from app.staff.routers import users as staff_users
from app.staff.routers import clubs as staff_clubs
from app.students.routers import users as student_users
from app.staff.routers import sections as staff_sections
from app.staff.routers import superadmin
from app.staff.routers import invitations
from app.core.database import check_database_health

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database with tables and initial data
    logger.info("Starting application initialization...")
    try:
        await init_database()
        logger.info("Database initialization completed successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise

    yield

    # Cleanup on shutdown
    logger.info("Application shutdown initiated")


app = FastAPI(
    title="Training API with Telegram Auth",
    description="A CRUD API with Telegram Web App authentication",
    version="1.0.0",
    lifespan=lifespan,
)

# Add rate limiter to app state
app.state.limiter = limiter

# Register exception handlers
register_exception_handlers(app)

# Add rate limit exception handler
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

# Include routers with API version prefix
app.include_router(staff_users.router, prefix="/api/v1")
app.include_router(staff_clubs.router, prefix="/api/v1")
app.include_router(staff_sections.router, prefix="/api/v1")
app.include_router(invitations.router, prefix="/api/v1")
app.include_router(student_users.router, prefix="/api/v1")
app.include_router(superadmin.router, prefix="/api/v1")


@app.get("/")
async def root():
    """
    Welcome endpoint
    """
    return {
        "message": "Training Mini App API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "ssl": "enabled",
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint with database connectivity check
    """
    db_healthy = await check_database_health()

    status = "healthy" if db_healthy else "unhealthy"

    return {
        "status": status,
        "service": "training-mini-app-api",
        "ssl": "enabled",
        "database": "connected" if db_healthy else "disconnected",
    }
