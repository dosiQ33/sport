from fastapi import FastAPI
from contextlib import asynccontextmanager
from slowapi.errors import RateLimitExceeded

from app.core.database import engine, Base
from app.core.limits import limiter, rate_limit_handler
from app.stuff.routers import users as stuff_users
from app.stuff.routers import clubs as stuff_clubs
from app.students.routers import users as student_users


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

# Include routers with API version prefix
app.include_router(stuff_users.router, prefix="/api/v1")
app.include_router(stuff_clubs.router, prefix="/api/v1")
app.include_router(student_users.router, prefix="/api/v1")


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
    }


@app.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "healthy", "service": "training-mini-app-api"}
