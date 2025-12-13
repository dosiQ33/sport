"""Student Routers Package"""
from .users import router as users_router
from .memberships import router as memberships_router
from .attendance import router as attendance_router
from .payments import router as payments_router
from .schedule import router as schedule_router
from .clubs import router as clubs_router

__all__ = [
    "users_router",
    "memberships_router",
    "attendance_router",
    "payments_router",
    "schedule_router",
    "clubs_router",
]
