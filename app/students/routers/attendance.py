"""Student Attendance Router - Endpoints for check-in and attendance tracking"""
import math
from datetime import date
from fastapi import APIRouter, Depends, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_student_user
from app.core.exceptions import NotFoundError
from app.students.crud.users import get_user_student_by_telegram_id
from app.students.crud.attendance import (
    check_in_student,
    get_student_attendance,
    get_attendance_stats,
)
from app.students.schemas.attendance import (
    CheckInRequest,
    CheckInResponse,
    AttendanceRecordRead,
    AttendanceListResponse,
    AttendanceStatsResponse,
)

router = APIRouter(prefix="/students/attendance", tags=["Student Attendance"])


@router.post("/checkin", response_model=CheckInResponse)
@limiter.limit("10/minute")
async def check_in(
    request: Request,
    checkin_request: Optional[CheckInRequest] = None,
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Record a check-in for the current user.
    
    Optionally provide location coordinates and lesson ID.
    Returns success status and attendance details.
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        return CheckInResponse(
            success=False,
            message="Student profile not found. Please register first."
        )
    
    if checkin_request is None:
        checkin_request = CheckInRequest()
    
    result = await check_in_student(db, student.id, checkin_request)
    
    return result


@router.get("/", response_model=AttendanceListResponse)
@limiter.limit("30/minute")
async def get_my_attendance(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    date_from: Optional[date] = Query(None, description="Filter from date"),
    date_to: Optional[date] = Query(None, description="Filter to date"),
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get attendance history.
    
    Returns paginated list of attendance records.
    Optionally filter by date range.
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        raise NotFoundError("Student", "Please register first")
    
    skip = (page - 1) * size
    records, total = await get_student_attendance(
        db, student.id, skip, size, date_from, date_to
    )
    
    pages = math.ceil(total / size) if total > 0 else 1
    
    return AttendanceListResponse(
        records=records,
        total=total,
        page=page,
        size=size,
        pages=pages
    )


@router.get("/stats", response_model=AttendanceStatsResponse)
@limiter.limit("30/minute")
async def get_my_attendance_stats(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get attendance statistics.
    
    Returns visits this month, missed sessions, average attendance, etc.
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        return AttendanceStatsResponse()
    
    stats = await get_attendance_stats(db, student.id)
    
    return stats
