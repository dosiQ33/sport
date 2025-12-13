"""Student Memberships Router - Endpoints for viewing and managing memberships"""
import math
from fastapi import APIRouter, Depends, Query, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_student_user
from app.core.exceptions import NotFoundError
from app.students.crud.users import get_user_student_by_telegram_id
from app.students.crud.memberships import (
    get_student_memberships,
    get_active_memberships,
    has_active_membership,
    get_membership_history,
    freeze_student_membership,
    unfreeze_student_membership,
    get_membership_stats,
)
from app.students.schemas.memberships import (
    MembershipRead,
    MembershipListResponse,
    MembershipHistoryResponse,
    FreezeMembershipRequest,
    UnfreezeMembershipRequest,
    MembershipStatsResponse,
)

router = APIRouter(prefix="/students/memberships", tags=["Student Memberships"])


@router.get("/", response_model=MembershipListResponse)
@limiter.limit("30/minute")
async def get_my_memberships(
    request: Request,
    include_inactive: bool = Query(False, description="Include expired/cancelled memberships"),
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Get current user's memberships.
    
    By default returns only active/frozen memberships.
    Set include_inactive=true to include expired/cancelled.
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        raise NotFoundError("Student", "Please register first")
    
    memberships = await get_student_memberships(db, student.id, include_inactive)
    
    return MembershipListResponse(
        memberships=memberships,
        total=len(memberships)
    )


@router.get("/active", response_model=MembershipListResponse)
@limiter.limit("60/minute")
async def get_my_active_memberships(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """Get only active memberships (active, new, frozen statuses)."""
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        raise NotFoundError("Student", "Please register first")
    
    memberships = await get_active_memberships(db, student.id)
    
    return MembershipListResponse(
        memberships=memberships,
        total=len(memberships)
    )


@router.get("/check", response_model=Dict[str, bool])
@limiter.limit("60/minute")
async def check_active_membership(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """Check if user has any active membership."""
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        return {"has_active_membership": False}
    
    has_membership = await has_active_membership(db, student.id)
    
    return {"has_active_membership": has_membership}


@router.get("/history", response_model=MembershipHistoryResponse)
@limiter.limit("20/minute")
async def get_my_membership_history(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """Get membership history (expired/cancelled memberships)."""
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        raise NotFoundError("Student", "Please register first")
    
    skip = (page - 1) * size
    history, total = await get_membership_history(db, student.id, skip, size)
    
    return MembershipHistoryResponse(
        history=history,
        total=total
    )


@router.get("/stats", response_model=MembershipStatsResponse)
@limiter.limit("30/minute")
async def get_my_membership_stats(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """Get membership statistics."""
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        return MembershipStatsResponse()
    
    stats = await get_membership_stats(db, student.id)
    
    return MembershipStatsResponse(**stats)


@router.post("/freeze", response_model=MembershipRead)
@limiter.limit("5/minute")
async def freeze_my_membership(
    request: Request,
    freeze_request: FreezeMembershipRequest,
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Freeze a membership.
    
    Membership must be active. Freeze days are limited by the membership's available freeze days.
    Maximum freeze period is 30 days.
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        raise NotFoundError("Student", "Please register first")
    
    membership = await freeze_student_membership(db, student.id, freeze_request)
    
    return membership


@router.post("/unfreeze", response_model=MembershipRead)
@limiter.limit("5/minute")
async def unfreeze_my_membership(
    request: Request,
    unfreeze_request: UnfreezeMembershipRequest,
    current_user: Dict[str, Any] = Depends(get_current_student_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Unfreeze a membership.
    
    Membership must be frozen. Unused freeze days are returned.
    """
    student = await get_user_student_by_telegram_id(db, current_user.get("id"))
    if not student:
        raise NotFoundError("Student", "Please register first")
    
    membership = await unfreeze_student_membership(db, student.id, unfreeze_request.enrollment_id)
    
    return membership
