"""Staff Students CRUD - Operations for managing students from staff perspective"""
import math
import logging
from typing import List, Optional, Tuple, Dict
from datetime import date, timedelta, datetime
from sqlalchemy import and_, or_, func, extract
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db_operation
from app.core.exceptions import NotFoundError, ValidationError, AuthorizationError
from app.core.telegram_sender import send_telegram_message, BotType
from app.staff.models.enrollments import StudentEnrollment, EnrollmentStatus
from app.staff.models.groups import Group
from app.staff.models.sections import Section
from app.staff.models.clubs import Club
from app.staff.models.users import UserStaff
from app.staff.models.user_roles import UserRole
from app.staff.models.roles import Role, RoleType
from app.staff.models.tariffs import Tariff
from app.staff.models.notifications import StaffNotification
from app.students.models.users import UserStudent
from app.students.models.attendance import StudentAttendance
from app.students.models.payments import StudentPayment
from app.staff.schemas.students import (
    StudentFilters, 
    StudentRead, 
    MembershipInfo,
    StudentAttendanceRecord,
    StudentAttendanceStats,
    StudentPaymentRecord,
    StudentPaymentStats,
)

logger = logging.getLogger(__name__)


async def get_user_accessible_club_ids(
    session: AsyncSession,
    user_id: int,
    role_filter: Optional[List[str]] = None
) -> List[int]:
    """Get club IDs where user has specific roles (owner, admin, or coach)"""
    query = (
        select(UserRole.club_id)
        .join(Role, UserRole.role_id == Role.id)
        .where(
            and_(
                UserRole.user_id == user_id,
                UserRole.is_active == True
            )
        )
    )
    
    if role_filter:
        role_types = [RoleType(r) for r in role_filter if r in ['owner', 'admin', 'coach']]
        if role_types:
            query = query.where(Role.code.in_(role_types))
    
    result = await session.execute(query)
    return [row[0] for row in result.fetchall()]


async def get_user_roles_in_clubs(
    session: AsyncSession,
    user_id: int
) -> Dict[int, RoleType]:
    """Get user's roles mapped by club_id -> RoleType"""
    query = (
        select(UserRole.club_id, Role.code)
        .join(Role, UserRole.role_id == Role.id)
        .where(
            and_(
                UserRole.user_id == user_id,
                UserRole.is_active == True
            )
        )
    )
    result = await session.execute(query)
    return {row[0]: row[1] for row in result.fetchall()}


async def get_coach_section_ids(
    session: AsyncSession,
    user_id: int
) -> List[int]:
    """Get section IDs where user is the coach"""
    query = (
        select(Section.id)
        .where(Section.coach_id == user_id)
    )
    result = await session.execute(query)
    return [row[0] for row in result.fetchall()]


async def get_coach_group_ids(
    session: AsyncSession,
    user_id: int
) -> List[int]:
    """Get group IDs where user is the coach"""
    query = (
        select(Group.id)
        .where(Group.coach_id == user_id)
    )
    result = await session.execute(query)
    return [row[0] for row in result.fetchall()]


@db_operation
async def get_students_for_staff(
    session: AsyncSession,
    staff_user_id: int,
    skip: int = 0,
    limit: int = 50,
    filters: Optional[StudentFilters] = None
) -> Tuple[List[StudentRead], int]:
    """
    Get students visible to the staff user based on their role:
    - Owner/Admin: All students in their clubs
    - Coach: Only students in their sections/groups
    """
    # Get user's roles in clubs
    user_roles = await get_user_roles_in_clubs(session, staff_user_id)
    
    if not user_roles:
        return [], 0
    
    # Determine which clubs user is owner/admin of
    owner_admin_club_ids = [
        club_id for club_id, role_id in user_roles.items()
        if role_id in [RoleType.owner, RoleType.admin]
    ]
    
    # Determine which clubs user is only a coach in
    coach_only_club_ids = [
        club_id for club_id, role_id in user_roles.items()
        if role_id == RoleType.coach and club_id not in owner_admin_club_ids
    ]
    
    # Get groups for owner/admin clubs
    owner_admin_group_ids = []
    if owner_admin_club_ids:
        query = (
            select(Group.id)
            .join(Section, Group.section_id == Section.id)
            .where(Section.club_id.in_(owner_admin_club_ids))
        )
        result = await session.execute(query)
        owner_admin_group_ids = [row[0] for row in result.fetchall()]
    
    # Get groups where user is coach (for coach-only clubs)
    coach_group_ids = []
    if coach_only_club_ids:
        coach_group_ids = await get_coach_group_ids(session, staff_user_id)
        # Filter to only include groups in coach-only clubs
        query = (
            select(Group.id)
            .join(Section, Group.section_id == Section.id)
            .where(
                and_(
                    Group.id.in_(coach_group_ids),
                    Section.club_id.in_(coach_only_club_ids)
                )
            )
        )
        result = await session.execute(query)
        coach_group_ids = [row[0] for row in result.fetchall()]
    
    # Combine accessible group IDs
    accessible_group_ids = list(set(owner_admin_group_ids + coach_group_ids))
    
    if not accessible_group_ids:
        return [], 0
    
    # Build main query
    base_query = (
        select(
            UserStudent,
            StudentEnrollment,
            Group,
            Section,
            Club,
            UserStaff
        )
        .select_from(StudentEnrollment)
        .join(UserStudent, StudentEnrollment.student_id == UserStudent.id)
        .join(Group, StudentEnrollment.group_id == Group.id)
        .join(Section, Group.section_id == Section.id)
        .join(Club, Section.club_id == Club.id)
        .outerjoin(UserStaff, Group.coach_id == UserStaff.id)
        .where(StudentEnrollment.group_id.in_(accessible_group_ids))
    )
    
    # Apply filters
    if filters:
        # Search filter
        if filters.search:
            search_term = f"%{filters.search.strip()}%"
            base_query = base_query.where(
                or_(
                    func.concat(UserStudent.first_name, ' ', UserStudent.last_name).ilike(search_term),
                    UserStudent.phone_number.ilike(search_term.replace(' ', ''))
                )
            )
        
        # Status filter
        if filters.status:
            base_query = base_query.where(StudentEnrollment.status == filters.status)
        
        # Club filter
        if filters.club_id:
            base_query = base_query.where(Section.club_id == filters.club_id)
        
        # Section filter
        if filters.section_id:
            base_query = base_query.where(Group.section_id == filters.section_id)
        
        # Group filter
        if filters.group_ids:
            base_query = base_query.where(Group.id.in_(filters.group_ids))
        
        # Coach filter
        if filters.coach_ids:
            base_query = base_query.where(Group.coach_id.in_(filters.coach_ids))
    
    # Count total
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0
    
    # Apply pagination and ordering
    query = base_query.order_by(UserStudent.created_at.desc()).offset(skip).limit(limit)
    
    result = await session.execute(query)
    rows = result.fetchall()
    
    # Transform to response
    students = []
    for row in rows:
        student, enrollment, group, section, club, coach = row
        
        membership = MembershipInfo(
            id=enrollment.id,
            status=enrollment.status,
            start_date=enrollment.start_date,
            end_date=enrollment.end_date,
            tariff_id=enrollment.tariff_id,
            tariff_name=enrollment.tariff_name,
            price=float(enrollment.price) if enrollment.price else 0,
            freeze_days_total=enrollment.freeze_days_total,
            freeze_days_used=enrollment.freeze_days_used,
            freeze_start_date=enrollment.freeze_start_date,
            freeze_end_date=enrollment.freeze_end_date,
        )
        
        coach_name = None
        if coach:
            coach_name = f"{coach.first_name} {coach.last_name or ''}".strip()
        
        students.append(StudentRead(
            id=student.id,
            telegram_id=student.telegram_id,
            first_name=student.first_name,
            last_name=student.last_name,
            phone_number=student.phone_number,
            username=student.username,
            photo_url=student.photo_url,
            club_id=club.id,
            club_name=club.name,
            section_id=section.id,
            section_name=section.name,
            group_id=group.id,
            group_name=group.name,
            coach_id=group.coach_id,
            coach_name=coach_name,
            membership=membership,
            created_at=student.created_at,
        ))
    
    return students, total


@db_operation
async def get_student_by_id_for_staff(
    session: AsyncSession,
    student_id: int,
    staff_user_id: int
) -> Optional[StudentRead]:
    """Get a specific student if accessible to the staff user"""
    students, _ = await get_students_for_staff(
        session,
        staff_user_id,
        skip=0,
        limit=1,
        filters=None
    )
    
    # Find the specific student
    for student in students:
        if student.id == student_id:
            return student
    
    return None


@db_operation
async def create_enrollment(
    session: AsyncSession,
    student_id: int,
    group_id: int,
    start_date: date,
    end_date: date,
    staff_user_id: int,
    tariff_id: Optional[int] = None,
    tariff_name: Optional[str] = None,
    price: float = 0,
    freeze_days_total: int = 0
) -> StudentEnrollment:
    """Create a new student enrollment"""
    # Verify staff has access to this group
    # Get group and check permissions
    group_query = (
        select(Group)
        .options(joinedload(Group.section))
        .where(Group.id == group_id)
    )
    result = await session.execute(group_query)
    group = result.scalar_one_or_none()
    
    if not group:
        raise NotFoundError("Group", str(group_id))
    
    # Check user has permission
    user_roles = await get_user_roles_in_clubs(session, staff_user_id)
    club_id = group.section.club_id
    
    if club_id not in user_roles:
        raise AuthorizationError("You don't have access to this club")
    
    role = user_roles[club_id]
    if role == RoleType.coach and group.coach_id != staff_user_id:
        raise AuthorizationError("Coaches can only manage students in their own groups")
    
    # Check if enrollment already exists
    existing_query = (
        select(StudentEnrollment)
        .where(
            and_(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.group_id == group_id,
                StudentEnrollment.is_active == True
            )
        )
    )
    existing_result = await session.execute(existing_query)
    if existing_result.scalar_one_or_none():
        raise ValidationError("Student is already enrolled in this group")
    
    # Determine initial status
    today = date.today()
    days_since_start = (today - start_date).days
    
    if days_since_start <= 14:
        status = EnrollmentStatus.new
    elif end_date < today:
        status = EnrollmentStatus.expired
    else:
        status = EnrollmentStatus.active
    
    enrollment = StudentEnrollment(
        student_id=student_id,
        group_id=group_id,
        status=status,
        start_date=start_date,
        end_date=end_date,
        tariff_id=tariff_id,
        tariff_name=tariff_name,
        price=price,
        freeze_days_total=freeze_days_total,
    )
    
    session.add(enrollment)
    await session.commit()
    
    # Reload enrollment with relationships for notification
    enrollment_query = (
        select(StudentEnrollment)
        .options(
            joinedload(StudentEnrollment.group)
            .joinedload(Group.section)
            .joinedload(Section.club)
        )
        .where(StudentEnrollment.id == enrollment.id)
    )
    enrollment_result = await session.execute(enrollment_query)
    enrollment = enrollment_result.scalar_one_or_none()
    
    # NOTIFICATION: Notify staff about new enrollment
    try:
        from app.staff.services.notification_service import send_membership_notification
        
        await send_membership_notification(
            session=session,
            notification_type='buy',
            student_id=student_id,
            enrollment=enrollment,
            additional_data={
                'tariff_id': tariff_id,
                'tariff_name': tariff_name or 'N/A',
                'price': price,
                'start_date': start_date,
                'end_date': end_date
            }
        )
    except Exception as e:
        logger.error(f"Failed to send enrollment notification: {e}", exc_info=True)
    
    return enrollment


@db_operation
async def extend_membership(
    session: AsyncSession,
    enrollment_id: int,
    days: int,
    staff_user_id: int,
    tariff_id: Optional[int] = None,
    tariff_name: Optional[str] = None,
    price: float = 0
) -> StudentEnrollment:
    """Extend a student's membership"""
    enrollment_query = (
        select(StudentEnrollment)
        .options(
            joinedload(StudentEnrollment.group).joinedload(Group.section)
        )
        .where(StudentEnrollment.id == enrollment_id)
    )
    result = await session.execute(enrollment_query)
    enrollment = result.scalar_one_or_none()
    
    if not enrollment:
        raise NotFoundError("Enrollment", str(enrollment_id))
    
    # Check permissions
    user_roles = await get_user_roles_in_clubs(session, staff_user_id)
    club_id = enrollment.group.section.club_id
    
    if club_id not in user_roles:
        raise AuthorizationError("You don't have access to this club")
    
    role = user_roles[club_id]
    if role == RoleType.coach and enrollment.group.coach_id != staff_user_id:
        raise AuthorizationError("Coaches can only manage students in their own groups")
    
    # Extend end date
    enrollment.end_date = enrollment.end_date + timedelta(days=days)
    enrollment.status = EnrollmentStatus.active
    
    if tariff_id:
        enrollment.tariff_id = tariff_id
    if tariff_name:
        enrollment.tariff_name = tariff_name
    if price:
        enrollment.price = price
    
    await session.commit()
    
    # NOTIFICATION: Notify staff about extension
    # Re-query enrollment with relationships after commit (objects are expired after commit)
    try:
        from app.staff.services.notification_service import send_membership_notification
        
        enrollment_for_notification = (
            select(StudentEnrollment)
            .options(
                joinedload(StudentEnrollment.group)
                .joinedload(Group.section)
                .joinedload(Section.club)
            )
            .where(StudentEnrollment.id == enrollment.id)
        )
        enrollment_result = await session.execute(enrollment_for_notification)
        enrollment_with_relations = enrollment_result.scalar_one_or_none()
        
        if enrollment_with_relations:
            await send_membership_notification(
                session=session,
                notification_type='extend',
                student_id=enrollment_with_relations.student_id,
                enrollment=enrollment_with_relations,
                additional_data={
                    'days': days,
                    'new_end_date': enrollment_with_relations.end_date,
                    'tariff_id': tariff_id,
                    'tariff_name': tariff_name
                }
            )
    except Exception as e:
        logger.error(f"Failed to send extension notification: {e}", exc_info=True)
    
    return enrollment


@db_operation
async def freeze_membership(
    session: AsyncSession,
    enrollment_id: int,
    days: int,
    staff_user_id: int,
    reason: Optional[str] = None
) -> StudentEnrollment:
    """Freeze a student's membership"""
    enrollment_query = (
        select(StudentEnrollment)
        .options(
            joinedload(StudentEnrollment.group).joinedload(Group.section).joinedload(Section.club)
        )
        .where(StudentEnrollment.id == enrollment_id)
    )
    result = await session.execute(enrollment_query)
    enrollment = result.scalar_one_or_none()
    
    if not enrollment:
        raise NotFoundError("Enrollment", str(enrollment_id))
    
    # Check permissions
    user_roles = await get_user_roles_in_clubs(session, staff_user_id)
    club_id = enrollment.group.section.club_id
    club = enrollment.group.section.club
    
    if club_id not in user_roles:
        raise AuthorizationError("You don't have access to this club")
    
    role = user_roles[club_id]
    if role == RoleType.coach and enrollment.group.coach_id != staff_user_id:
        raise AuthorizationError("Coaches can only manage students in their own groups")
    
    # Check freeze days available
    available_freeze_days = enrollment.freeze_days_total - enrollment.freeze_days_used
    if days > available_freeze_days:
        raise ValidationError(f"Only {available_freeze_days} freeze days available")
    
    # Get student information for notifications
    student_query = select(UserStudent).where(UserStudent.id == enrollment.student_id)
    student_result = await session.execute(student_query)
    student = student_result.scalar_one_or_none()
    
    # Apply freeze
    today = date.today()
    enrollment.status = EnrollmentStatus.frozen
    enrollment.freeze_start_date = today
    enrollment.freeze_end_date = today + timedelta(days=days)
    enrollment.freeze_days_used += days
    enrollment.end_date = enrollment.end_date + timedelta(days=days)
    
    # Create notifications for club owners and admins
    try:
        # Get all owners and admins of this club
        staff_recipients_query = (
            select(UserRole.user_id)
            .join(Role, UserRole.role_id == Role.id)
            .where(
                and_(
                    UserRole.club_id == club_id,
                    UserRole.is_active == True,
                    Role.code.in_([RoleType.owner, RoleType.admin])
                )
            )
        )
        staff_recipients_result = await session.execute(staff_recipients_query)
        staff_recipient_ids = [row[0] for row in staff_recipients_result.fetchall()]
        
        student_name = f"{student.first_name} {student.last_name or ''}".strip() if student else "Unknown"
        freeze_end_date = (today + timedelta(days=days)).strftime("%d.%m.%Y")
        new_membership_end = enrollment.end_date.strftime("%d.%m.%Y")
        
        # Create in-app notification for each staff member
        for recipient_id in staff_recipient_ids:
            notification = StaffNotification(
                recipient_id=recipient_id,
                title="Заморозка абонемента",
                message=f"Абонемент студента {student_name} заморожен на {days} дней. "
                        f"Дата окончания заморозки: {freeze_end_date}. "
                        f"Новая дата окончания абонемента: {new_membership_end}.",
                metadata_json={
                    "type": "membership_freeze",
                    "student_id": enrollment.student_id,
                    "group_id": enrollment.group_id,
                    "days": days,
                    "enrollment_id": enrollment_id,
                    "club_id": club_id,
                }
            )
            session.add(notification)
        
        logger.info(f"Created freeze notifications for {len(staff_recipient_ids)} staff members")
        
    except Exception as e:
        logger.error(f"Failed to create staff notifications: {str(e)}")
    
    # Send Telegram notification to student
    if student and student.telegram_id:
        try:
            club_name = club.name if club else "клуба"
            freeze_end_date = (today + timedelta(days=days)).strftime("%d.%m.%Y")
            new_membership_end = enrollment.end_date.strftime("%d.%m.%Y")
            
            message = (
                f"❄️ <b>Ваш абонемент заморожен</b>\n\n"
                f"Клуб: {club_name}\n"
                f"Количество дней: {days}\n"
                f"Дата окончания заморозки: {freeze_end_date}\n"
                f"Новая дата окончания абонемента: {new_membership_end}\n"
            )
            if reason:
                message += f"\nПричина: {reason}"
            
            await send_telegram_message(
                chat_id=student.telegram_id,
                text=message,
                bot_type=BotType.STUDENT
            )
            logger.info(f"Sent freeze notification to student {student.telegram_id}")
            
        except Exception as e:
            logger.error(f"Failed to send Telegram notification to student: {str(e)}")
    
    await session.commit()
    await session.refresh(enrollment)
    
    return enrollment


@db_operation
async def unfreeze_membership(
    session: AsyncSession,
    enrollment_id: int,
    staff_user_id: int
) -> StudentEnrollment:
    """Unfreeze a student's membership"""
    enrollment_query = (
        select(StudentEnrollment)
        .options(
            joinedload(StudentEnrollment.group).joinedload(Group.section).joinedload(Section.club)
        )
        .where(StudentEnrollment.id == enrollment_id)
    )
    result = await session.execute(enrollment_query)
    enrollment = result.scalar_one_or_none()
    
    if not enrollment:
        raise NotFoundError("Enrollment", str(enrollment_id))
    
    if enrollment.status != EnrollmentStatus.frozen:
        raise ValidationError("Membership is not frozen")
    
    # Check permissions
    user_roles = await get_user_roles_in_clubs(session, staff_user_id)
    club_id = enrollment.group.section.club_id
    club = enrollment.group.section.club
    
    if club_id not in user_roles:
        raise AuthorizationError("You don't have access to this club")
    
    # Get student information for notifications
    student_query = select(UserStudent).where(UserStudent.id == enrollment.student_id)
    student_result = await session.execute(student_query)
    student = student_result.scalar_one_or_none()
    
    # Calculate remaining freeze days and adjust end date
    today = date.today()
    unused_days = 0
    if enrollment.freeze_end_date and enrollment.freeze_end_date > today:
        unused_days = (enrollment.freeze_end_date - today).days
        enrollment.end_date = enrollment.end_date - timedelta(days=unused_days)
        enrollment.freeze_days_used -= unused_days
    
    enrollment.status = EnrollmentStatus.active
    enrollment.freeze_start_date = None
    enrollment.freeze_end_date = None
    
    # Send Telegram notification to student
    if student and student.telegram_id:
        try:
            club_name = club.name if club else "клуба"
            membership_end = enrollment.end_date.strftime("%d.%m.%Y")
            
            message = (
                f"✅ <b>Ваш абонемент разморожен</b>\n\n"
                f"Клуб: {club_name}\n"
                f"Дата окончания абонемента: {membership_end}\n"
            )
            if unused_days > 0:
                message += f"\nВозвращено неиспользованных дней заморозки: {unused_days}"
            
            await send_telegram_message(
                chat_id=student.telegram_id,
                text=message,
                bot_type=BotType.STUDENT
            )
            logger.info(f"Sent unfreeze notification to student {student.telegram_id}")
            
        except Exception as e:
            logger.error(f"Failed to send Telegram notification to student: {str(e)}")
    
    await session.commit()
    await session.refresh(enrollment)
    
    return enrollment


# ===== Student Attendance for Staff =====

@db_operation
async def get_student_attendance_for_staff(
    session: AsyncSession,
    student_id: int,
    staff_user_id: int,
    skip: int = 0,
    limit: int = 20,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None
) -> Tuple[List[StudentAttendanceRecord], int]:
    """
    Get student's attendance history.
    Staff can only see attendance for students they have access to.
    """
    # First verify staff has access to this student
    student = await get_student_by_id_for_staff(session, student_id, staff_user_id)
    if not student:
        raise NotFoundError("Student", str(student_id))
    
    # Build query for attendance records
    base_query = (
        select(
            StudentAttendance,
            Club.name.label("club_name"),
            Section.name.label("section_name"),
            Group.name.label("group_name"),
            UserStaff.first_name.label("coach_first_name"),
            UserStaff.last_name.label("coach_last_name"),
        )
        .select_from(StudentAttendance)
        .outerjoin(Club, StudentAttendance.club_id == Club.id)
        .outerjoin(Section, StudentAttendance.section_id == Section.id)
        .outerjoin(Group, StudentAttendance.group_id == Group.id)
        .outerjoin(UserStaff, Group.coach_id == UserStaff.id)
        .where(StudentAttendance.student_id == student_id)
    )
    
    # Apply date filters
    if date_from:
        base_query = base_query.where(StudentAttendance.checkin_date >= date_from)
    if date_to:
        base_query = base_query.where(StudentAttendance.checkin_date <= date_to)
    
    # Count total
    count_query = select(func.count()).select_from(
        StudentAttendance
    ).where(StudentAttendance.student_id == student_id)
    
    if date_from:
        count_query = count_query.where(StudentAttendance.checkin_date >= date_from)
    if date_to:
        count_query = count_query.where(StudentAttendance.checkin_date <= date_to)
    
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0
    
    # Apply pagination and ordering
    query = base_query.order_by(StudentAttendance.checkin_date.desc()).offset(skip).limit(limit)
    
    result = await session.execute(query)
    rows = result.fetchall()
    
    # Transform to response
    records = []
    for row in rows:
        attendance = row[0]
        club_name = row[1]
        section_name = row[2]
        group_name = row[3]
        coach_first = row[4]
        coach_last = row[5]
        
        coach_name = None
        if coach_first:
            coach_name = f"{coach_first} {coach_last or ''}".strip()
        
        time_str = None
        if attendance.checkin_time:
            time_str = attendance.checkin_time.strftime("%H:%M")
        
        records.append(StudentAttendanceRecord(
            id=attendance.id,
            date=attendance.checkin_date,
            time=time_str,
            club_id=attendance.club_id,
            club_name=club_name,
            section_id=attendance.section_id,
            section_name=section_name,
            group_id=attendance.group_id,
            group_name=group_name,
            lesson_id=attendance.lesson_id,
            coach_name=coach_name,
            status=attendance.status or "attended",
        ))
    
    return records, total


@db_operation
async def get_student_attendance_stats_for_staff(
    session: AsyncSession,
    student_id: int,
    staff_user_id: int
) -> StudentAttendanceStats:
    """Get attendance statistics for a student."""
    # Verify access
    student = await get_student_by_id_for_staff(session, student_id, staff_user_id)
    if not student:
        raise NotFoundError("Student", str(student_id))
    
    today = date.today()
    month_start = today.replace(day=1)
    
    # Total visits
    total_query = select(func.count()).select_from(StudentAttendance).where(
        and_(
            StudentAttendance.student_id == student_id,
            StudentAttendance.status == "attended"
        )
    )
    total_result = await session.execute(total_query)
    total_visits = total_result.scalar() or 0
    
    # Visits this month
    month_visits_query = select(func.count()).select_from(StudentAttendance).where(
        and_(
            StudentAttendance.student_id == student_id,
            StudentAttendance.status == "attended",
            StudentAttendance.checkin_date >= month_start
        )
    )
    month_result = await session.execute(month_visits_query)
    visits_this_month = month_result.scalar() or 0
    
    # Missed this month
    missed_query = select(func.count()).select_from(StudentAttendance).where(
        and_(
            StudentAttendance.student_id == student_id,
            StudentAttendance.status == "missed",
            StudentAttendance.checkin_date >= month_start
        )
    )
    missed_result = await session.execute(missed_query)
    missed_this_month = missed_result.scalar() or 0
    
    # Late this month
    late_query = select(func.count()).select_from(StudentAttendance).where(
        and_(
            StudentAttendance.student_id == student_id,
            StudentAttendance.status == "late",
            StudentAttendance.checkin_date >= month_start
        )
    )
    late_result = await session.execute(late_query)
    late_this_month = late_result.scalar() or 0
    
    # Calculate attendance rate
    total_month = visits_this_month + missed_this_month + late_this_month
    attendance_rate = 0.0
    if total_month > 0:
        attendance_rate = round((visits_this_month + late_this_month) / total_month * 100, 1)
    
    return StudentAttendanceStats(
        total_visits=total_visits,
        visits_this_month=visits_this_month,
        missed_this_month=missed_this_month,
        late_this_month=late_this_month,
        attendance_rate=attendance_rate,
    )


# ===== Student Payments for Staff =====

@db_operation
async def get_student_payments_for_staff(
    session: AsyncSession,
    student_id: int,
    staff_user_id: int,
    skip: int = 0,
    limit: int = 20,
    status_filter: Optional[str] = None
) -> Tuple[List[StudentPaymentRecord], int]:
    """
    Get student's payment history.
    Staff can only see payments for students they have access to.
    """
    # First verify staff has access to this student
    student = await get_student_by_id_for_staff(session, student_id, staff_user_id)
    if not student:
        raise NotFoundError("Student", str(student_id))
    
    # Build query for payment records
    base_query = (
        select(
            StudentPayment,
            Club.name.label("club_name"),
            Tariff.name.label("tariff_name"),
        )
        .select_from(StudentPayment)
        .outerjoin(Club, StudentPayment.club_id == Club.id)
        .outerjoin(Tariff, StudentPayment.tariff_id == Tariff.id)
        .where(StudentPayment.student_id == student_id)
    )
    
    # Apply status filter
    if status_filter:
        base_query = base_query.where(StudentPayment.status == status_filter)
    
    # Count total
    count_query = select(func.count()).select_from(
        StudentPayment
    ).where(StudentPayment.student_id == student_id)
    
    if status_filter:
        count_query = count_query.where(StudentPayment.status == status_filter)
    
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0
    
    # Apply pagination and ordering
    query = base_query.order_by(StudentPayment.created_at.desc()).offset(skip).limit(limit)
    
    result = await session.execute(query)
    rows = result.fetchall()
    
    # Transform to response
    payments = []
    for row in rows:
        payment = row[0]
        club_name = row[1]
        tariff_name = row[2]
        
        # Determine operation type based on description or context
        operation_type = "purchase"
        if payment.description:
            desc_lower = payment.description.lower()
            if "продление" in desc_lower or "extend" in desc_lower or "renewal" in desc_lower:
                operation_type = "renewal"
            elif "возврат" in desc_lower or "refund" in desc_lower:
                operation_type = "refund"
        
        payment_date = payment.payment_date or payment.created_at
        if hasattr(payment_date, 'date'):
            payment_date = payment_date.date()
        
        payments.append(StudentPaymentRecord(
            id=payment.id,
            date=payment_date,
            amount=float(payment.amount),
            currency=payment.currency or "KZT",
            club_id=payment.club_id,
            club_name=club_name,
            tariff_id=payment.tariff_id,
            tariff_name=tariff_name,
            operation_type=operation_type,
            status=payment.status.value if hasattr(payment.status, 'value') else str(payment.status),
            payment_method=payment.payment_method.value if payment.payment_method and hasattr(payment.payment_method, 'value') else None,
        ))
    
    return payments, total


@db_operation
async def get_student_payment_stats_for_staff(
    session: AsyncSession,
    student_id: int,
    staff_user_id: int
) -> StudentPaymentStats:
    """Get payment statistics for a student."""
    # Verify access
    student = await get_student_by_id_for_staff(session, student_id, staff_user_id)
    if not student:
        raise NotFoundError("Student", str(student_id))
    
    # Total paid amount
    paid_query = select(func.sum(StudentPayment.amount)).where(
        and_(
            StudentPayment.student_id == student_id,
            StudentPayment.status == "paid"
        )
    )
    paid_result = await session.execute(paid_query)
    total_paid = float(paid_result.scalar() or 0)
    
    # Payments count
    count_query = select(func.count()).select_from(StudentPayment).where(
        and_(
            StudentPayment.student_id == student_id,
            StudentPayment.status == "paid"
        )
    )
    count_result = await session.execute(count_query)
    payments_count = count_result.scalar() or 0
    
    # Last payment date
    last_payment_query = select(StudentPayment.payment_date).where(
        and_(
            StudentPayment.student_id == student_id,
            StudentPayment.status == "paid"
        )
    ).order_by(StudentPayment.payment_date.desc()).limit(1)
    last_result = await session.execute(last_payment_query)
    last_payment = last_result.scalar_one_or_none()
    
    last_payment_date = None
    if last_payment:
        if hasattr(last_payment, 'date'):
            last_payment_date = last_payment.date()
        else:
            last_payment_date = last_payment
    
    # Pending amount
    pending_query = select(func.sum(StudentPayment.amount)).where(
        and_(
            StudentPayment.student_id == student_id,
            StudentPayment.status == "pending"
        )
    )
    pending_result = await session.execute(pending_query)
    pending_amount = float(pending_result.scalar() or 0)
    
    return StudentPaymentStats(
        total_paid=total_paid,
        payments_count=payments_count,
        last_payment_date=last_payment_date,
        pending_amount=pending_amount,
    )
