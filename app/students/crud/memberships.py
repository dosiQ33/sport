"""Student Memberships CRUD - Operations for viewing enrollments from student perspective"""
import math
from typing import List, Tuple, Optional
from datetime import date, timedelta
from sqlalchemy import and_, func
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db_operation
from app.core.exceptions import NotFoundError, ValidationError, AuthorizationError
from app.staff.models.enrollments import StudentEnrollment, EnrollmentStatus
from app.staff.models.groups import Group
from app.staff.models.sections import Section
from app.staff.models.clubs import Club
from app.staff.models.users import UserStaff
from app.students.models.users import UserStudent
from app.students.schemas.memberships import (
    MembershipRead,
    MembershipHistoryRead,
    MembershipStatus,
    FreezeMembershipRequest,
)


@db_operation
async def get_student_memberships(
    session: AsyncSession,
    student_id: int,
    include_inactive: bool = False
) -> List[MembershipRead]:
    """Get all memberships for a student"""
    query = (
        select(
            StudentEnrollment,
            Group,
            Section,
            Club,
            UserStaff
        )
        .select_from(StudentEnrollment)
        .join(Group, StudentEnrollment.group_id == Group.id)
        .join(Section, Group.section_id == Section.id)
        .join(Club, Section.club_id == Club.id)
        .outerjoin(UserStaff, Group.coach_id == UserStaff.id)
        .where(StudentEnrollment.student_id == student_id)
    )
    
    if not include_inactive:
        query = query.where(
            StudentEnrollment.status.in_([
                EnrollmentStatus.active,
                EnrollmentStatus.frozen,
                EnrollmentStatus.new,
                EnrollmentStatus.scheduled
            ])
        )
    
    query = query.order_by(StudentEnrollment.created_at.desc())
    
    result = await session.execute(query)
    rows = result.fetchall()
    
    memberships = []
    for row in rows:
        enrollment, group, section, club, coach = row
        
        coach_name = None
        if coach:
            coach_name = f"{coach.first_name} {coach.last_name or ''}".strip()
        
        # Calculate freeze days available
        freeze_days_available = (enrollment.freeze_days_total or 0) - (enrollment.freeze_days_used or 0)
        
        memberships.append(MembershipRead(
            id=enrollment.id,
            club_id=club.id,
            club_name=club.name,
            section_id=section.id,
            section_name=section.name,
            group_id=group.id,
            group_name=group.name,
            training_type="Group",
            level=group.level,
            status=MembershipStatus(enrollment.status.value),
            start_date=enrollment.start_date,
            end_date=enrollment.end_date,
            tariff_id=enrollment.tariff_id,
            tariff_name=enrollment.tariff_name,
            price=float(enrollment.price) if enrollment.price else 0,
            freeze_days_available=freeze_days_available,
            freeze_days_used=enrollment.freeze_days_used or 0,
            freeze_start_date=enrollment.freeze_start_date,
            freeze_end_date=enrollment.freeze_end_date,
            coach_id=group.coach_id,
            coach_name=coach_name,
            created_at=enrollment.created_at,
        ))
    
    return memberships


@db_operation
async def get_active_memberships(
    session: AsyncSession,
    student_id: int
) -> List[MembershipRead]:
    """Get only active memberships for a student"""
    return await get_student_memberships(session, student_id, include_inactive=False)


@db_operation
async def has_active_membership(
    session: AsyncSession,
    student_id: int
) -> bool:
    """Check if student has any active membership"""
    query = (
        select(func.count(StudentEnrollment.id))
        .where(
            and_(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status.in_([
                    EnrollmentStatus.active,
                    EnrollmentStatus.new
                ])
            )
        )
    )
    result = await session.execute(query)
    count = result.scalar()
    return count > 0


@db_operation
async def get_membership_history(
    session: AsyncSession,
    student_id: int,
    skip: int = 0,
    limit: int = 20
) -> Tuple[List[MembershipHistoryRead], int]:
    """Get membership history (expired/cancelled)"""
    base_query = (
        select(
            StudentEnrollment,
            Group,
            Section,
            Club
        )
        .select_from(StudentEnrollment)
        .join(Group, StudentEnrollment.group_id == Group.id)
        .join(Section, Group.section_id == Section.id)
        .join(Club, Section.club_id == Club.id)
        .where(
            and_(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status.in_([
                    EnrollmentStatus.expired,
                    EnrollmentStatus.cancelled
                ])
            )
        )
    )
    
    # Count
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0
    
    # Get paginated results
    query = base_query.order_by(StudentEnrollment.updated_at.desc()).offset(skip).limit(limit)
    result = await session.execute(query)
    rows = result.fetchall()
    
    history = []
    for row in rows:
        enrollment, group, section, club = row
        
        reason = "expired" if enrollment.status == EnrollmentStatus.expired else "cancelled"
        
        history.append(MembershipHistoryRead(
            id=enrollment.id,
            club_id=club.id,
            club_name=club.name,
            section_id=section.id,
            section_name=section.name,
            group_id=group.id,
            group_name=group.name,
            training_type="Group",
            deactivation_date=enrollment.end_date,
            reason=reason,
            start_date=enrollment.start_date,
            end_date=enrollment.end_date,
        ))
    
    return history, total


@db_operation
async def freeze_student_membership(
    session: AsyncSession,
    student_id: int,
    request: FreezeMembershipRequest
) -> MembershipRead:
    """Freeze a student's membership"""
    # Get enrollment
    enrollment_query = (
        select(StudentEnrollment)
        .options(
            joinedload(StudentEnrollment.group).joinedload(Group.section)
        )
        .where(
            and_(
                StudentEnrollment.id == request.enrollment_id,
                StudentEnrollment.student_id == student_id
            )
        )
    )
    result = await session.execute(enrollment_query)
    enrollment = result.scalar_one_or_none()
    
    if not enrollment:
        raise NotFoundError("Membership", str(request.enrollment_id))
    
    if enrollment.status not in [EnrollmentStatus.active, EnrollmentStatus.new]:
        raise ValidationError("Can only freeze active memberships")
    
    # Calculate freeze days
    freeze_days = (request.end_date - request.start_date).days
    
    if freeze_days < 1:
        raise ValidationError("Freeze period must be at least 1 day")
    
    if freeze_days > 30:
        raise ValidationError("Maximum freeze period is 30 days")
    
    # Check available freeze days
    available_freeze_days = (enrollment.freeze_days_total or 0) - (enrollment.freeze_days_used or 0)
    if freeze_days > available_freeze_days:
        raise ValidationError(f"Only {available_freeze_days} freeze days available")
    
    # Apply freeze
    enrollment.status = EnrollmentStatus.frozen
    enrollment.freeze_start_date = request.start_date
    enrollment.freeze_end_date = request.end_date
    enrollment.freeze_days_used = (enrollment.freeze_days_used or 0) + freeze_days
    enrollment.end_date = enrollment.end_date + timedelta(days=freeze_days)
    
    # CASCADE: Shift scheduled memberships in the same club
    # Get club_id from the frozen enrollment's group -> section
    club_id = enrollment.group.section.club_id
    
    scheduled_query = (
        select(StudentEnrollment)
        .join(Group, StudentEnrollment.group_id == Group.id)
        .join(Section, Group.section_id == Section.id)
        .where(
            and_(
                StudentEnrollment.student_id == student_id,
                Section.club_id == club_id,
                StudentEnrollment.status == EnrollmentStatus.scheduled
            )
        )
    )
    scheduled_result = await session.execute(scheduled_query)
    scheduled_memberships = scheduled_result.scalars().all()
    
    for scheduled in scheduled_memberships:
        # Shift both start and end dates by freeze_days
        scheduled.start_date = scheduled.start_date + timedelta(days=freeze_days)
        scheduled.end_date = scheduled.end_date + timedelta(days=freeze_days)
    
    await session.commit()
    await session.refresh(enrollment)

    # NOTIFICATION: Notify the coach/staff
    try:
        from app.core.telegram_sender import send_telegram_message
        from app.students.crud.users import get_student_by_id

        # Get student details for the message
        student_info = await get_student_by_id(session, student_id)
        student_name = f"{student_info.first_name} {student_info.last_name or ''}".strip()
        
        # Determine who to notify (Coach of the group)
        # enrollment.group is already loaded via joinedload
        coach_id = enrollment.group.coach_id
        
        if coach_id:
            from app.staff.models.users import UserStaff
            # Get coach's telegram_id
            coach = await session.get(UserStaff, coach_id)
            
            if coach and coach.telegram_id:
                message = (
                    f"❄️ <b>Freeze Notification</b>\n\n"
                    f"Student: <b>{student_name}</b>\n"
                    f"Group: {enrollment.group.name}\n"
                    f"Period: {request.start_date.strftime('%d.%m.%Y')} - {request.end_date.strftime('%d.%m.%Y')}\n"
                    f"Days: {freeze_days}"
                )
                # We use create_task to not block the response
                import asyncio
                asyncio.create_task(send_telegram_message(coach.telegram_id, message))
            
            # In-App Notification
            try:
                from app.staff.crud.notifications import create_notification
                from app.staff.schemas.notifications import NotificationCreate
                
                notification_data = NotificationCreate(
                    recipient_id=coach.id,
                    title="❄️ Абонемент заморожен",
                    message=f"Студент {student_name} заморозил абонемент в группе {enrollment.group.name} на {freeze_days} дней.",
                    metadata_json={
                        "type": "membership_freeze",
                        "student_id": student_id,
                        "group_id": enrollment.group_id,
                        "days": freeze_days
                    }
                )
                await create_notification(session, notification_data)
            except Exception as e:
                    logging.getLogger(__name__).error(f"Failed to create in-app notification: {e}")
    except Exception as e:
        # Log error but don't fail the request
        import logging
        logging.getLogger(__name__).error(f"Failed to send freeze notification: {e}")
    
    # Get full membership data for response
    memberships = await get_student_memberships(session, student_id, include_inactive=True)
    for m in memberships:
        if m.id == enrollment.id:
            return m
    
    raise NotFoundError("Membership", str(request.enrollment_id))


@db_operation
async def unfreeze_student_membership(
    session: AsyncSession,
    student_id: int,
    enrollment_id: int
) -> MembershipRead:
    """Unfreeze a student's membership"""
    # Get enrollment
    enrollment_query = (
        select(StudentEnrollment)
        .options(
            joinedload(StudentEnrollment.group).joinedload(Group.section)
        )
        .where(
            and_(
                StudentEnrollment.id == enrollment_id,
                StudentEnrollment.student_id == student_id
            )
        )
    )
    result = await session.execute(enrollment_query)
    enrollment = result.scalar_one_or_none()
    
    if not enrollment:
        raise NotFoundError("Membership", str(enrollment_id))
    
    if enrollment.status != EnrollmentStatus.frozen:
        raise ValidationError("Membership is not frozen")
    
    # Calculate unused freeze days and adjust end date
    today = date.today()
    days_to_shift_back = 0
    if enrollment.freeze_end_date and enrollment.freeze_end_date > today:
        unused_days = (enrollment.freeze_end_date - today).days
        enrollment.end_date = enrollment.end_date - timedelta(days=unused_days)
        enrollment.freeze_days_used = (enrollment.freeze_days_used or 0) - unused_days
        days_to_shift_back = unused_days
    
    enrollment.status = EnrollmentStatus.active
    enrollment.freeze_start_date = None
    enrollment.freeze_end_date = None
    
    # CASCADE: Shift scheduled memberships back in the same club
    if days_to_shift_back > 0:
        club_id = enrollment.group.section.club_id
        
        scheduled_query = (
            select(StudentEnrollment)
            .join(Group, StudentEnrollment.group_id == Group.id)
            .join(Section, Group.section_id == Section.id)
            .where(
                and_(
                    StudentEnrollment.student_id == student_id,
                    Section.club_id == club_id,
                    StudentEnrollment.status == EnrollmentStatus.scheduled
                )
            )
        )
        scheduled_result = await session.execute(scheduled_query)
        scheduled_memberships = scheduled_result.scalars().all()
        
        for scheduled in scheduled_memberships:
            # Shift both start and end dates back
            scheduled.start_date = scheduled.start_date - timedelta(days=days_to_shift_back)
            scheduled.end_date = scheduled.end_date - timedelta(days=days_to_shift_back)
    
    await session.commit()
    await session.refresh(enrollment)
    
    # Get full membership data for response
    memberships = await get_student_memberships(session, student_id, include_inactive=True)
    for m in memberships:
        if m.id == enrollment.id:
            return m
    
    raise NotFoundError("Membership", str(enrollment_id))


@db_operation
async def get_membership_stats(
    session: AsyncSession,
    student_id: int
) -> dict:
    """Get membership statistics for a student"""
    # Count active memberships
    active_query = (
        select(func.count(StudentEnrollment.id))
        .where(
            and_(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status.in_([EnrollmentStatus.active, EnrollmentStatus.new])
            )
        )
    )
    active_result = await session.execute(active_query)
    active_count = active_result.scalar() or 0
    
    # Count frozen memberships
    frozen_query = (
        select(func.count(StudentEnrollment.id))
        .where(
            and_(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status == EnrollmentStatus.frozen
            )
        )
    )
    frozen_result = await session.execute(frozen_query)
    frozen_count = frozen_result.scalar() or 0
    
    # Total memberships
    total_query = (
        select(func.count(StudentEnrollment.id))
        .where(StudentEnrollment.student_id == student_id)
    )
    total_result = await session.execute(total_query)
    total_count = total_result.scalar() or 0
    
    # Get nearest expiry and freeze days available
    active_memberships_query = (
        select(StudentEnrollment)
        .where(
            and_(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status.in_([EnrollmentStatus.active, EnrollmentStatus.new])
            )
        )
        .order_by(StudentEnrollment.end_date.asc())
    )
    active_result = await session.execute(active_memberships_query)
    active_memberships = active_result.scalars().all()
    
    days_until_expiry = None
    total_freeze_days_available = 0
    
    today = date.today()
    for membership in active_memberships:
        if days_until_expiry is None:
            days_until_expiry = (membership.end_date - today).days
        total_freeze_days_available += (membership.freeze_days_total or 0) - (membership.freeze_days_used or 0)
    
    return {
        "active_memberships": active_count,
        "frozen_memberships": frozen_count,
        "total_memberships": total_count,
        "days_until_expiry": days_until_expiry,
        "freeze_days_available": total_freeze_days_available,
    }
