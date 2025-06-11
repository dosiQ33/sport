import logging
from fastapi import FastAPI, Request
from contextlib import asynccontextmanager
from slowapi.errors import RateLimitExceeded
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import engine, Base
from app.core.limits import limiter, rate_limit_handler
from app.stuff.routers import users as stuff_users
from app.stuff.routers import clubs as stuff_clubs
from app.students.routers import users as student_users
from app.stuff.routers import sections as stuff_sections

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="Training API with Telegram Auth",
    description="A CRUD API with Telegram Web App authentication",
    version="1.0.0",
    lifespan=lifespan,
)

# Add rate limiter to app state
app.state.limiter = limiter

# Add rate limit exception handler
app.add_exception_handler(RateLimitExceeded, rate_limit_handler)

# CORS middleware - обновленный с вашим доменом
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


# Middleware для логирования запросов
@app.middleware("http")
async def log_requests(request: Request, call_next):
    logger.info(f"🔍 Request URL: {request.url}")
    logger.info(f"🌐 Origin: {request.headers.get('origin')}")
    logger.info(f"🤖 User-Agent: {request.headers.get('user-agent')}")
    logger.info(f"🔗 Referer: {request.headers.get('referer')}")
    logger.info(f"📱 Method: {request.method}")

    response = await call_next(request)

    logger.info(f"✅ Response Status: {response.status_code}")
    return response


# Include routers with API version prefix
app.include_router(stuff_users.router, prefix="/api/v1")
app.include_router(stuff_clubs.router, prefix="/api/v1")
app.include_router(student_users.router, prefix="/api/v1")
app.include_router(stuff_sections.router, prefix="/api/v1")


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
    Health check endpoint
    """
    return {"status": "healthy", "service": "training-mini-app-api", "ssl": "enabled"}
