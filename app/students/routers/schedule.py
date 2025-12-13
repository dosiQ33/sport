"""Student Schedule Router - Endpoints for viewing training sessions"""
import math
from datetime import date
from fastapi import APIRouter, Depends, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional, List

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_student_user
from app.core.exceptions import NotFoundError
from app.students.crud.users import get_user_student_by_telegram_id
from app.students.crud.schedule import (
    get_student_upcoming_sessions,
    get_all_available_sessions,
    get_trainers_for_student,
)
from app.students.schemas.schedule import (
    SessionRead,
    SessionListResponse,
    TrainerInfo,
    ScheduleFilters,
)

router = APIRouter(prefix="/students/schedule", tags=["Student Schedule"])


@router.get("/next", response_model=List[SessionRead])
@limiter.limit("60/minute")
async def get_next_sessions(
    request: Request,
    limit: int = Query(10, ge=1, le=50, description="Number of sessions to return"),
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get upcoming training sessions.
    
    Returns the next sessions from groups where the student is enrolled.
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        return []
    
    sessions = await get_student_upcoming_sessions(db, student.id, limit)
    
    return sessions


@router.get("/sessions", response_model=SessionListResponse)
@limiter.limit("30/minute")
async def get_all_sessions(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    club_id: Optional[int] = Query(None, description="Filter by club"),
    section_id: Optional[int] = Query(None, description="Filter by section"),
    trainer_id: Optional[int] = Query(None, description="Filter by trainer"),
    date_from: Optional[date] = Query(None, description="Filter from date"),
    date_to: Optional[date] = Query(None, description="Filter to date"),
    only_my_sessions: bool = Query(False, description="Show only enrolled sessions"),
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get all available training sessions with filters.
    
    Returns paginated list of sessions.
    Can filter by club, section, trainer, date range.
    Set only_my_sessions=true to show only sessions from enrolled groups.
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        raise NotFoundError("Student", "Please register first")
    
    filters = ScheduleFilters(
        club_id=club_id,
        section_id=section_id,
        trainer_id=trainer_id,
        date_from=date_from,
        date_to=date_to,
        only_my_sessions=only_my_sessions,
    )
    
    skip = (page - 1) * size
    sessions, total = await get_all_available_sessions(
        db, student.id, filters, skip, size
    )
    
    return SessionListResponse(
        sessions=sessions,
        total=total
    )


@router.get("/trainers", response_model=List[TrainerInfo])
@limiter.limit("30/minute")
async def get_trainers(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get list of trainers.
    
    Returns trainers from clubs where the student has memberships.
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        return []
    
    trainers = await get_trainers_for_student(db, student.id)
    
    return trainers
