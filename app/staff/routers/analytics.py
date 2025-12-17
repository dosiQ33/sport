"""Staff Analytics Router - Endpoints for club analytics and dashboard"""
from fastapi import APIRouter, Depends, Query, Request, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_staff_user
from app.core.exceptions import NotFoundError
from app.staff.crud.users import get_user_staff_by_telegram_id
from app.staff.crud.analytics import (
    get_club_analytics,
    get_dashboard_summary,
)
from app.staff.schemas.analytics import (
    ClubAnalyticsResponse,
    DashboardSummary,
)

router = APIRouter(prefix="/staff/analytics", tags=["Staff Analytics"])


@router.get("/clubs/{club_id}", response_model=ClubAnalyticsResponse)
@limiter.limit("30/minute")
async def get_club_analytics_endpoint(
    request: Request,
    club_id: int = Path(..., description="Club ID"),
    period_days: int = Query(30, ge=7, le=365, description="Period in days for analytics"),
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get analytics for a specific club.
    
    Returns:
    - Student counts (total, active, new this month)
    - Training stats (conducted, scheduled, cancelled)
    - Section breakdown with student counts
    
    Access rules:
    - Owner/Admin: Full club analytics
    - Coach: Only their sections' analytics
    
    Parameters:
    - **club_id**: ID of the club
    - **period_days**: Period in days for analytics (default: 30, max: 365)
    """
    staff_user = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not staff_user:
        raise NotFoundError("Staff user", "Please register as staff first")
    
    analytics = await get_club_analytics(
        db,
        club_id=club_id,
        staff_user_id=staff_user.id,
        period_days=period_days,
    )
    
    return analytics


@router.get("/dashboard", response_model=DashboardSummary)
@limiter.limit("30/minute")
async def get_dashboard_summary_endpoint(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get summary dashboard data for all clubs accessible to the user.
    
    Returns aggregated stats across all clubs:
    - Total clubs, sections, groups, students
    - Trainings this month
    - New students this month
    """
    staff_user = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not staff_user:
        raise NotFoundError("Staff user", "Please register as staff first")
    
    summary = await get_dashboard_summary(
        db,
        staff_user_id=staff_user.id,
    )
    
    return summary
