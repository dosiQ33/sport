"""Staff Students CRUD - Operations for managing students from staff perspective"""
import math
from typing import List, Optional, Tuple
from datetime import date, timedelta
from sqlalchemy import and_, or_, func
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db_operation
from app.core.exceptions import NotFoundError, ValidationError, ForbiddenError
from app.staff.models.enrollments import StudentEnrollment, EnrollmentStatus
from app.staff.models.groups import Group
from app.staff.models.sections import Section
from app.staff.models.clubs import Club
from app.staff.models.users import UserStaff
from app.staff.models.user_roles import UserRole
from app.staff.models.roles import RoleType
from app.students.models.users import UserStudent
from app.staff.schemas.students import StudentFilters, StudentRead, MembershipInfo


async def get_user_accessible_club_ids(
    session: AsyncSession,
    user_id: int,
    role_filter: Optional[List[str]] = None
) -> List[int]:
    """Get club IDs where user has specific roles (owner, admin, or coach)"""
    query = (
        select(UserRole.club_id)
        .where(
            and_(
                UserRole.user_id == user_id,
                UserRole.is_active == True
            )
        )
    )
    
    if role_filter:
        role_conditions = [UserRole.role_id == RoleType[r] for r in role_filter if r in ['owner', 'admin', 'coach']]
        if role_conditions:
            query = query.where(or_(*role_conditions))
    
    result = await session.execute(query)
    return [row[0] for row in result.fetchall()]


async def get_user_roles_in_clubs(
    session: AsyncSession,
    user_id: int
) -> dict:
    """Get user's roles mapped by club_id"""
    query = (
        select(UserRole.club_id, UserRole.role_id)
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
        raise ForbiddenError("You don't have access to this club")
    
    role = user_roles[club_id]
    if role == RoleType.coach and group.coach_id != staff_user_id:
        raise ForbiddenError("Coaches can only manage students in their own groups")
    
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
    await session.refresh(enrollment)
    
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
        raise ForbiddenError("You don't have access to this club")
    
    role = user_roles[club_id]
    if role == RoleType.coach and enrollment.group.coach_id != staff_user_id:
        raise ForbiddenError("Coaches can only manage students in their own groups")
    
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
    await session.refresh(enrollment)
    
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
        raise ForbiddenError("You don't have access to this club")
    
    role = user_roles[club_id]
    if role == RoleType.coach and enrollment.group.coach_id != staff_user_id:
        raise ForbiddenError("Coaches can only manage students in their own groups")
    
    # Check freeze days available
    available_freeze_days = enrollment.freeze_days_total - enrollment.freeze_days_used
    if days > available_freeze_days:
        raise ValidationError(f"Only {available_freeze_days} freeze days available")
    
    # Apply freeze
    today = date.today()
    enrollment.status = EnrollmentStatus.frozen
    enrollment.freeze_start_date = today
    enrollment.freeze_end_date = today + timedelta(days=days)
    enrollment.freeze_days_used += days
    enrollment.end_date = enrollment.end_date + timedelta(days=days)
    
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
            joinedload(StudentEnrollment.group).joinedload(Group.section)
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
    
    if club_id not in user_roles:
        raise ForbiddenError("You don't have access to this club")
    
    # Calculate remaining freeze days and adjust end date
    today = date.today()
    if enrollment.freeze_end_date and enrollment.freeze_end_date > today:
        unused_days = (enrollment.freeze_end_date - today).days
        enrollment.end_date = enrollment.end_date - timedelta(days=unused_days)
        enrollment.freeze_days_used -= unused_days
    
    enrollment.status = EnrollmentStatus.active
    enrollment.freeze_start_date = None
    enrollment.freeze_end_date = None
    
    await session.commit()
    await session.refresh(enrollment)
    
    return enrollment
