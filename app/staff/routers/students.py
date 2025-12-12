"""Staff Students Router - Endpoints for staff to manage students"""
from fastapi import APIRouter, Depends, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional, List

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_staff_user
from app.core.exceptions import NotFoundError, AuthorizationError
from app.staff.crud.users import get_user_staff_by_telegram_id
from app.staff.crud.students import (
    get_students_for_staff,
    get_student_by_id_for_staff,
    create_enrollment,
    extend_membership,
    freeze_membership,
    unfreeze_membership,
)
from app.staff.schemas.students import (
    StudentRead,
    StudentListResponse,
    StudentFilters,
    ExtendMembershipRequest,
    FreezeMembershipRequest,
    CreateEnrollmentRequest,
    EnrollmentStatusEnum,
)

router = APIRouter(prefix="/staff/students", tags=["Staff Students"])


@router.get("/", response_model=StudentListResponse)
@limiter.limit("30/minute")
async def get_students_list(
    request: Request,
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    size: int = Query(50, ge=1, le=100, description="Number of items per page"),
    search: Optional[str] = Query(None, description="Search by name or phone"),
    status: Optional[EnrollmentStatusEnum] = Query(None, description="Filter by status"),
    club_id: Optional[int] = Query(None, description="Filter by club"),
    section_id: Optional[int] = Query(None, description="Filter by section"),
    group_ids: Optional[str] = Query(None, description="Filter by group IDs (comma-separated)"),
    coach_ids: Optional[str] = Query(None, description="Filter by coach IDs (comma-separated)"),
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get list of students visible to the current staff user.
    
    Access rules:
    - Owner/Admin: See all students in their clubs
    - Coach: See only students in their sections/groups
    
    Filters:
    - search: Search by name or phone (partial match)
    - status: Filter by membership status (active, frozen, expired, cancelled, new)
    - club_id: Filter by specific club
    - section_id: Filter by specific section
    - group_ids: Filter by specific groups (comma-separated)
    - coach_ids: Filter by specific coaches (comma-separated)
    """
    # Get staff user
    staff_user = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not staff_user:
        raise NotFoundError("Staff user", "Please register as staff first")
    
    # Parse comma-separated IDs
    parsed_group_ids = None
    if group_ids:
        try:
            parsed_group_ids = [int(x.strip()) for x in group_ids.split(",") if x.strip()]
        except ValueError:
            parsed_group_ids = None
    
    parsed_coach_ids = None
    if coach_ids:
        try:
            parsed_coach_ids = [int(x.strip()) for x in coach_ids.split(",") if x.strip()]
        except ValueError:
            parsed_coach_ids = None
    
    # Build filters
    filters = StudentFilters(
        search=search,
        status=status,
        club_id=club_id,
        section_id=section_id,
        group_ids=parsed_group_ids,
        coach_ids=parsed_coach_ids,
    )
    
    skip = (page - 1) * size
    
    students, total = await get_students_for_staff(
        db,
        staff_user_id=staff_user.id,
        skip=skip,
        limit=size,
        filters=filters if any([search, status, club_id, section_id, parsed_group_ids, parsed_coach_ids]) else None
    )
    
    pages = math.ceil(total / size) if total > 0 else 1
    
    return StudentListResponse(
        students=students,
        total=total,
        page=page,
        size=size,
        pages=pages,
        filters=filters
    )


@router.get("/{student_id}", response_model=StudentRead)
@limiter.limit("30/minute")
async def get_student(
    request: Request,
    student_id: int,
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get a specific student by ID.
    
    Returns student only if the current staff user has access to view them.
    """
    staff_user = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not staff_user:
        raise NotFoundError("Staff user", "Please register as staff first")
    
    student = await get_student_by_id_for_staff(db, student_id, staff_user.id)
    
    if not student:
        raise NotFoundError("Student", str(student_id))
    
    return student


@router.post("/enroll", status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def enroll_student(
    request: Request,
    enrollment_data: CreateEnrollmentRequest,
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Enroll a student in a group.
    
    Creates a new enrollment/membership for the student.
    """
    staff_user = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not staff_user:
        raise NotFoundError("Staff user", "Please register as staff first")
    
    enrollment = await create_enrollment(
        db,
        student_id=enrollment_data.student_id,
        group_id=enrollment_data.group_id,
        start_date=enrollment_data.start_date,
        end_date=enrollment_data.end_date,
        staff_user_id=staff_user.id,
        tariff_id=enrollment_data.tariff_id,
        price=enrollment_data.price,
        freeze_days_total=enrollment_data.freeze_days_total,
    )
    
    return {"message": "Student enrolled successfully", "enrollment_id": enrollment.id}


@router.post("/extend")
@limiter.limit("10/minute")
async def extend_student_membership(
    request: Request,
    data: ExtendMembershipRequest,
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Extend a student's membership.
    
    Adds the specified number of days to the membership end date.
    """
    staff_user = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not staff_user:
        raise NotFoundError("Staff user", "Please register as staff first")
    
    enrollment = await extend_membership(
        db,
        enrollment_id=data.enrollment_id,
        days=data.days,
        staff_user_id=staff_user.id,
        tariff_id=data.tariff_id,
    )
    
    return {
        "message": "Membership extended successfully",
        "new_end_date": enrollment.end_date.isoformat(),
    }


@router.post("/freeze")
@limiter.limit("10/minute")
async def freeze_student_membership(
    request: Request,
    data: FreezeMembershipRequest,
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Freeze a student's membership.
    
    Temporarily suspends the membership for the specified number of days.
    The freeze period is added to the membership end date.
    """
    staff_user = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not staff_user:
        raise NotFoundError("Staff user", "Please register as staff first")
    
    enrollment = await freeze_membership(
        db,
        enrollment_id=data.enrollment_id,
        days=data.days,
        staff_user_id=staff_user.id,
        reason=data.reason,
    )
    
    return {
        "message": "Membership frozen successfully",
        "freeze_end_date": enrollment.freeze_end_date.isoformat() if enrollment.freeze_end_date else None,
        "new_end_date": enrollment.end_date.isoformat(),
    }


@router.post("/unfreeze/{enrollment_id}")
@limiter.limit("10/minute")
async def unfreeze_student_membership(
    request: Request,
    enrollment_id: int,
    current_user: Dict[str, Any] = Depends(get_current_staff_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Unfreeze a student's membership.
    
    Resumes the membership immediately. Any unused freeze days are returned.
    """
    staff_user = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not staff_user:
        raise NotFoundError("Staff user", "Please register as staff first")
    
    enrollment = await unfreeze_membership(
        db,
        enrollment_id=enrollment_id,
        staff_user_id=staff_user.id,
    )
    
    return {
        "message": "Membership unfrozen successfully",
        "status": enrollment.status.value,
        "end_date": enrollment.end_date.isoformat(),
    }
