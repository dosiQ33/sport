"""Staff Analytics CRUD - Operations for club and coach analytics"""
from typing import List, Optional
from datetime import date, timedelta
from sqlalchemy import and_, or_, func, extract
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db_operation
from app.core.exceptions import NotFoundError, AuthorizationError
from app.staff.models.enrollments import StudentEnrollment, EnrollmentStatus
from app.staff.models.groups import Group
from app.staff.models.sections import Section
from app.staff.models.clubs import Club
from app.staff.models.users import UserStaff
from app.staff.models.user_roles import UserRole
from app.staff.models.roles import Role, RoleType
from app.staff.models.lessons import Lesson
from app.staff.schemas.analytics import (
    ClubAnalyticsResponse,
    SectionStats,
    CoachAnalyticsResponse,
    DashboardSummary,
)


async def get_user_role_in_club(
    session: AsyncSession,
    user_id: int,
    club_id: int
) -> Optional[RoleType]:
    """Get user's role in a specific club"""
    query = (
        select(Role.code)
        .select_from(UserRole)
        .join(Role, UserRole.role_id == Role.id)
        .where(
            and_(
                UserRole.user_id == user_id,
                UserRole.club_id == club_id,
                UserRole.is_active == True
            )
        )
    )
    result = await session.execute(query)
    role = result.scalar_one_or_none()
    return role


@db_operation
async def get_club_analytics(
    session: AsyncSession,
    club_id: int,
    staff_user_id: int,
    period_days: int = 30
) -> ClubAnalyticsResponse:
    """
    Get analytics for a specific club.
    
    - Owner/Admin: Full club analytics
    - Coach: Only their sections' analytics
    """
    # Check permissions
    role = await get_user_role_in_club(session, staff_user_id, club_id)
    if not role:
        raise AuthorizationError("You don't have access to this club")
    
    # Get club
    club_query = select(Club).where(Club.id == club_id)
    club_result = await session.execute(club_query)
    club = club_result.scalar_one_or_none()
    
    if not club:
        raise NotFoundError("Club", str(club_id))
    
    # Calculate period
    today = date.today()
    period_start = today - timedelta(days=period_days)
    period_end = today
    month_start = today.replace(day=1)
    
    # Base filter - if coach, filter to their sections only
    section_filter = Section.club_id == club_id
    
    if role == RoleType.coach:
        # Get coach's section IDs
        coach_sections_query = select(Section.id).where(
            and_(
                Section.club_id == club_id,
                Section.coach_id == staff_user_id
            )
        )
        coach_sections_result = await session.execute(coach_sections_query)
        coach_section_ids = [row[0] for row in coach_sections_result.fetchall()]
        
        if not coach_section_ids:
            # Coach has no sections in this club
            return ClubAnalyticsResponse(
                club_id=club_id,
                club_name=club.name,
                period_start=period_start,
                period_end=period_end,
                sections=[],
            )
        
        section_filter = Section.id.in_(coach_section_ids)
    
    # Get sections with stats
    sections_query = (
        select(Section)
        .where(section_filter)
        .order_by(Section.name)
    )
    sections_result = await session.execute(sections_query)
    sections = sections_result.scalars().all()
    
    section_stats = []
    total_students = 0
    active_students = 0
    new_students_this_month = 0
    
    for section in sections:
        # Count groups in section
        groups_query = select(func.count()).select_from(Group).where(
            Group.section_id == section.id
        )
        groups_result = await session.execute(groups_query)
        groups_count = groups_result.scalar() or 0
        
        # Count students in section's groups
        students_query = (
            select(func.count(func.distinct(StudentEnrollment.student_id)))
            .select_from(StudentEnrollment)
            .join(Group, StudentEnrollment.group_id == Group.id)
            .where(
                and_(
                    Group.section_id == section.id,
                    StudentEnrollment.is_active == True
                )
            )
        )
        students_result = await session.execute(students_query)
        students_count = students_result.scalar() or 0
        
        section_stats.append(SectionStats(
            id=section.id,
            name=section.name,
            students_count=students_count,
            groups_count=groups_count,
        ))
        
        total_students += students_count
        
        # Count active students (active or new status)
        active_query = (
            select(func.count(func.distinct(StudentEnrollment.student_id)))
            .select_from(StudentEnrollment)
            .join(Group, StudentEnrollment.group_id == Group.id)
            .where(
                and_(
                    Group.section_id == section.id,
                    StudentEnrollment.is_active == True,
                    StudentEnrollment.status.in_([EnrollmentStatus.active, EnrollmentStatus.new])
                )
            )
        )
        active_result = await session.execute(active_query)
        active_students += active_result.scalar() or 0
        
        # Count new students this month
        new_query = (
            select(func.count(func.distinct(StudentEnrollment.student_id)))
            .select_from(StudentEnrollment)
            .join(Group, StudentEnrollment.group_id == Group.id)
            .where(
                and_(
                    Group.section_id == section.id,
                    StudentEnrollment.created_at >= month_start
                )
            )
        )
        new_result = await session.execute(new_query)
        new_students_this_month += new_result.scalar() or 0
    
    # Get section IDs for lesson filtering
    section_ids = [s.id for s in sections]
    
    # Training stats - get group IDs first
    groups_query = select(Group.id).where(Group.section_id.in_(section_ids))
    groups_result = await session.execute(groups_query)
    group_ids = [row[0] for row in groups_result.fetchall()]
    
    trainings_this_month = 0
    trainings_conducted = 0
    trainings_scheduled = 0
    trainings_cancelled = 0
    
    if group_ids:
        # Total trainings this month
        total_lessons_query = select(func.count()).select_from(Lesson).where(
            and_(
                Lesson.group_id.in_(group_ids),
                Lesson.planned_date >= month_start,
                Lesson.planned_date <= period_end
            )
        )
        total_result = await session.execute(total_lessons_query)
        trainings_this_month = total_result.scalar() or 0
        
        # Conducted (completed)
        conducted_query = select(func.count()).select_from(Lesson).where(
            and_(
                Lesson.group_id.in_(group_ids),
                Lesson.planned_date >= month_start,
                Lesson.planned_date <= period_end,
                Lesson.status == "completed"
            )
        )
        conducted_result = await session.execute(conducted_query)
        trainings_conducted = conducted_result.scalar() or 0
        
        # Scheduled (future)
        scheduled_query = select(func.count()).select_from(Lesson).where(
            and_(
                Lesson.group_id.in_(group_ids),
                Lesson.planned_date > today,
                Lesson.status == "scheduled"
            )
        )
        scheduled_result = await session.execute(scheduled_query)
        trainings_scheduled = scheduled_result.scalar() or 0
        
        # Cancelled
        cancelled_query = select(func.count()).select_from(Lesson).where(
            and_(
                Lesson.group_id.in_(group_ids),
                Lesson.planned_date >= month_start,
                Lesson.planned_date <= period_end,
                Lesson.status == "cancelled"
            )
        )
        cancelled_result = await session.execute(cancelled_query)
        trainings_cancelled = cancelled_result.scalar() or 0
    
    return ClubAnalyticsResponse(
        club_id=club_id,
        club_name=club.name,
        total_students=total_students,
        active_students=active_students,
        new_students_this_month=new_students_this_month,
        trainings_this_month=trainings_this_month,
        trainings_conducted=trainings_conducted,
        trainings_scheduled=trainings_scheduled,
        trainings_cancelled=trainings_cancelled,
        sections=section_stats,
        period_start=period_start,
        period_end=period_end,
    )


@db_operation
async def get_dashboard_summary(
    session: AsyncSession,
    staff_user_id: int
) -> DashboardSummary:
    """
    Get summary dashboard data for all clubs accessible to the user.
    """
    today = date.today()
    month_start = today.replace(day=1)
    
    # Get all clubs where user has a role
    clubs_query = (
        select(UserRole.club_id)
        .join(Role, UserRole.role_id == Role.id)
        .where(
            and_(
                UserRole.user_id == staff_user_id,
                UserRole.is_active == True
            )
        )
    )
    clubs_result = await session.execute(clubs_query)
    club_ids = [row[0] for row in clubs_result.fetchall()]
    
    if not club_ids:
        return DashboardSummary(
            period_start=month_start,
            period_end=today,
        )
    
    # Count clubs
    total_clubs = len(club_ids)
    
    # Count sections
    sections_query = select(func.count()).select_from(Section).where(
        Section.club_id.in_(club_ids)
    )
    sections_result = await session.execute(sections_query)
    total_sections = sections_result.scalar() or 0
    
    # Count groups
    groups_query = (
        select(func.count())
        .select_from(Group)
        .join(Section, Group.section_id == Section.id)
        .where(Section.club_id.in_(club_ids))
    )
    groups_result = await session.execute(groups_query)
    total_groups = groups_result.scalar() or 0
    
    # Get all group IDs
    group_ids_query = (
        select(Group.id)
        .join(Section, Group.section_id == Section.id)
        .where(Section.club_id.in_(club_ids))
    )
    group_ids_result = await session.execute(group_ids_query)
    group_ids = [row[0] for row in group_ids_result.fetchall()]
    
    total_students = 0
    new_students_this_month = 0
    trainings_this_month = 0
    
    if group_ids:
        # Count total students
        students_query = (
            select(func.count(func.distinct(StudentEnrollment.student_id)))
            .where(
                and_(
                    StudentEnrollment.group_id.in_(group_ids),
                    StudentEnrollment.is_active == True
                )
            )
        )
        students_result = await session.execute(students_query)
        total_students = students_result.scalar() or 0
        
        # New students this month
        new_query = (
            select(func.count(func.distinct(StudentEnrollment.student_id)))
            .where(
                and_(
                    StudentEnrollment.group_id.in_(group_ids),
                    StudentEnrollment.created_at >= month_start
                )
            )
        )
        new_result = await session.execute(new_query)
        new_students_this_month = new_result.scalar() or 0
        
        # Trainings this month
        trainings_query = select(func.count()).select_from(Lesson).where(
            and_(
                Lesson.group_id.in_(group_ids),
                Lesson.planned_date >= month_start,
                Lesson.planned_date <= today
            )
        )
        trainings_result = await session.execute(trainings_query)
        trainings_this_month = trainings_result.scalar() or 0
    
    return DashboardSummary(
        total_clubs=total_clubs,
        total_sections=total_sections,
        total_groups=total_groups,
        total_students=total_students,
        trainings_this_month=trainings_this_month,
        new_students_this_month=new_students_this_month,
        period_start=month_start,
        period_end=today,
    )
