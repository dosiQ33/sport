"""Student Clubs Router - Endpoints for viewing available clubs"""
import math
from fastapi import APIRouter, Depends, Query, status, Request, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional, List

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_student_user
from app.core.exceptions import NotFoundError
from app.students.crud.users import get_user_student_by_telegram_id
from app.students.crud.clubs import (
    get_clubs_list,
    get_club_details,
    get_student_club_ids,
    get_nearest_club,
)
from app.students.schemas.clubs import (
    ClubRead,
    ClubDetailRead,
    ClubListResponse,
    NearestClubResponse,
)

router = APIRouter(prefix="/students/clubs", tags=["Student Clubs"])


@router.get("/", response_model=ClubListResponse)
@limiter.limit("30/minute")
async def get_clubs(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search by name"),
    only_my_clubs: bool = Query(False, description="Show only clubs with memberships"),
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get list of clubs.
    
    Returns paginated list of clubs.
    Set only_my_clubs=true to show only clubs where user has memberships.
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    student_id = student.id if student else 0
    
    skip = (page - 1) * size
    clubs, total = await get_clubs_list(
        db, student_id, skip, size, search, only_my_clubs
    )
    
    pages = math.ceil(total / size) if total > 0 else 1
    
    return ClubListResponse(
        clubs=clubs,
        total=total,
        page=page,
        size=size,
        pages=pages
    )


@router.get("/my", response_model=List[int])
@limiter.limit("30/minute")
async def get_my_club_ids(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get IDs of clubs where user has active memberships.
    
    Useful for filtering UI elements.
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        return []
    
    club_ids = await get_student_club_ids(db, student.id)
    
    return club_ids


@router.get("/nearest", response_model=NearestClubResponse)
@limiter.limit("30/minute")
async def get_nearest_club_endpoint(
    request: Request,
    lat: float = Query(..., ge=-90, le=90, description="User latitude"),
    lon: float = Query(..., ge=-180, le=180, description="User longitude"),
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get the nearest club to user's location.
    
    Returns club info and distance in meters.
    Prioritizes clubs where user has memberships.
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    student_id = student.id if student else None
    
    result = await get_nearest_club(db, lat, lon, student_id)
    
    return result


@router.get("/{club_id}", response_model=ClubDetailRead)
@limiter.limit("30/minute")
async def get_club_detail(
    request: Request,
    club_id: int = Path(..., description="Club ID"),
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get detailed club information.
    
    Returns club info with sections and available tariffs.
    """
    club = await get_club_details(db, club_id)
    
    return club
