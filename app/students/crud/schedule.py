"""Student Schedule CRUD - Operations for viewing upcoming sessions"""
import math
from typing import List, Tuple, Optional
from datetime import date, datetime, timedelta
from sqlalchemy import and_, or_, func
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db_operation
from app.core.exceptions import NotFoundError, ValidationError
from app.staff.models.lessons import Lesson
from app.staff.models.groups import Group
from app.staff.models.sections import Section
from app.staff.models.clubs import Club
from app.staff.models.users import UserStaff
from app.staff.models.enrollments import StudentEnrollment, EnrollmentStatus
from app.students.models.bookings import LessonBooking
from app.students.schemas.schedule import (
    SessionRead,
    SessionStatus,
    ScheduleFilters,
    TrainerInfo,
)


@db_operation
async def get_student_upcoming_sessions(
    session: AsyncSession,
    student_id: int,
    limit: int = 10,
    include_all_clubs: bool = False
) -> List[SessionRead]:
    """Get upcoming training sessions for a student"""
    today = date.today()
    
    if include_all_clubs:
        # Get all upcoming lessons from clubs where student has membership
        enrollment_query = (
            select(StudentEnrollment.group_id, Section.club_id)
            .select_from(StudentEnrollment)
            .join(Group, StudentEnrollment.group_id == Group.id)
            .join(Section, Group.section_id == Section.id)
            .where(
                and_(
                    StudentEnrollment.student_id == student_id,
                    StudentEnrollment.status.in_([EnrollmentStatus.active, EnrollmentStatus.new])
                )
            )
        )
        enrollment_result = await session.execute(enrollment_query)
        enrollments = enrollment_result.fetchall()
        
        if not enrollments:
            return []
        
        group_ids = [e[0] for e in enrollments]
        
        # Get lessons for these groups
        lessons_query = (
            select(Lesson, Group, Section, Club, UserStaff)
            .select_from(Lesson)
            .join(Group, Lesson.group_id == Group.id)
            .join(Section, Group.section_id == Section.id)
            .join(Club, Section.club_id == Club.id)
            .outerjoin(UserStaff, Lesson.coach_id == UserStaff.id)
            .where(
                and_(
                    Lesson.group_id.in_(group_ids),
                    Lesson.planned_date >= today,
                    Lesson.status != "cancelled"
                )
            )
            .order_by(Lesson.planned_date.asc(), Lesson.planned_start_time.asc())
            .limit(limit)
        )
    else:
        # Get only lessons from groups where student is enrolled
        enrollment_query = (
            select(StudentEnrollment.group_id)
            .where(
                and_(
                    StudentEnrollment.student_id == student_id,
                    StudentEnrollment.status.in_([EnrollmentStatus.active, EnrollmentStatus.new])
                )
            )
        )
        enrollment_result = await session.execute(enrollment_query)
        group_ids = [row[0] for row in enrollment_result.fetchall()]
        
        if not group_ids:
            return []
        
        lessons_query = (
            select(Lesson, Group, Section, Club, UserStaff)
            .select_from(Lesson)
            .join(Group, Lesson.group_id == Group.id)
            .join(Section, Group.section_id == Section.id)
            .join(Club, Section.club_id == Club.id)
            .outerjoin(UserStaff, Lesson.coach_id == UserStaff.id)
            .where(
                and_(
                    Lesson.group_id.in_(group_ids),
                    Lesson.planned_date >= today,
                    Lesson.status != "cancelled"
                )
            )
            .order_by(Lesson.planned_date.asc(), Lesson.planned_start_time.asc())
            .limit(limit)
        )
    
    result = await session.execute(lessons_query)
    rows = result.fetchall()
    
    # Get all lesson IDs for booking queries
    lesson_ids = [row[0].id for row in rows]
    
    # Get booking counts for all lessons
    booking_counts = {}
    if lesson_ids:
        counts_query = (
            select(LessonBooking.lesson_id, func.count(LessonBooking.id))
            .where(
                and_(
                    LessonBooking.lesson_id.in_(lesson_ids),
                    LessonBooking.status == "booked"
                )
            )
            .group_by(LessonBooking.lesson_id)
        )
        counts_result = await session.execute(counts_query)
        booking_counts = {row[0]: row[1] for row in counts_result.fetchall()}
    
    # Get student's bookings (including excused)
    student_bookings = {}
    if lesson_ids:
        student_booking_query = (
            select(LessonBooking.lesson_id, LessonBooking.status)
            .where(
                and_(
                    LessonBooking.student_id == student_id,
                    LessonBooking.lesson_id.in_(lesson_ids),
                    LessonBooking.status.in_(["booked", "waitlist", "excused"])
                )
            )
        )
        student_booking_result = await session.execute(student_booking_query)
        student_bookings = {row[0]: row[1] for row in student_booking_result.fetchall()}
    
    sessions = []
    for row in rows:
        lesson, group, section, club, coach = row
        
        coach_name = None
        if coach:
            coach_name = f"{coach.first_name} {coach.last_name or ''}".strip()
        
        # Get booking info
        participants_count = booking_counts.get(lesson.id, 0)
        booking_status = student_bookings.get(lesson.id)
        is_booked = booking_status == "booked"
        is_in_waitlist = booking_status == "waitlist"
        is_excused = booking_status == "excused"
        
        # Determine status
        status = SessionStatus.scheduled
        if lesson.status == "cancelled":
            status = SessionStatus.cancelled
        elif is_booked:
            status = SessionStatus.booked
        elif group.capacity and participants_count >= group.capacity:
            status = SessionStatus.full
        
        sessions.append(SessionRead(
            id=lesson.id,
            section_name=section.name,
            group_name=group.name,
            coach_id=lesson.coach_id,
            coach_name=coach_name,
            club_id=club.id,
            club_name=club.name,
            club_address=club.address,
            date=lesson.planned_date,
            time=lesson.planned_start_time.strftime("%H:%M") if lesson.planned_start_time else "00:00",
            duration_minutes=lesson.duration_minutes,
            location=lesson.location,
            participants_count=participants_count,
            max_participants=group.capacity,
            status=status,
            is_booked=is_booked,
            is_in_waitlist=is_in_waitlist,
            is_excused=is_excused,
            notes=lesson.notes,
        ))
    
    return sessions


@db_operation
async def get_all_available_sessions(
    session: AsyncSession,
    student_id: int,
    filters: Optional[ScheduleFilters] = None,
    skip: int = 0,
    limit: int = 20
) -> Tuple[List[SessionRead], int]:
    """Get all available training sessions with filters"""
    today = date.today()
    
    # Get student's enrolled club IDs for filtering "my sessions"
    enrollment_query = (
        select(Section.club_id, StudentEnrollment.group_id)
        .select_from(StudentEnrollment)
        .join(Group, StudentEnrollment.group_id == Group.id)
        .join(Section, Group.section_id == Section.id)
        .where(
            and_(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status.in_([EnrollmentStatus.active, EnrollmentStatus.new])
            )
        )
    )
    enrollment_result = await session.execute(enrollment_query)
    enrollments = enrollment_result.fetchall()
    
    enrolled_club_ids = list(set([e[0] for e in enrollments]))
    enrolled_group_ids = [e[1] for e in enrollments]
    
    # Build base query
    base_query = (
        select(Lesson, Group, Section, Club, UserStaff)
        .select_from(Lesson)
        .join(Group, Lesson.group_id == Group.id)
        .join(Section, Group.section_id == Section.id)
        .join(Club, Section.club_id == Club.id)
        .outerjoin(UserStaff, Lesson.coach_id == UserStaff.id)
        .where(
            and_(
                Lesson.planned_date >= today,
                Lesson.status != "cancelled"
            )
        )
    )
    
    # Apply filters
    if filters:
        if filters.only_my_sessions and enrolled_group_ids:
            base_query = base_query.where(Lesson.group_id.in_(enrolled_group_ids))
        
        if filters.club_id:
            base_query = base_query.where(Section.club_id == filters.club_id)
        
        if filters.section_id:
            base_query = base_query.where(Group.section_id == filters.section_id)
        
        if filters.trainer_id:
            base_query = base_query.where(Lesson.coach_id == filters.trainer_id)
        
        if filters.date_from:
            base_query = base_query.where(Lesson.planned_date >= filters.date_from)
        
        if filters.date_to:
            base_query = base_query.where(Lesson.planned_date <= filters.date_to)
    
    # Count total
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0
    
    # Get paginated results
    query = (
        base_query
        .order_by(Lesson.planned_date.asc(), Lesson.planned_start_time.asc())
        .offset(skip)
        .limit(limit)
    )
    
    result = await session.execute(query)
    rows = result.fetchall()
    
    # Get all lesson IDs for booking queries
    lesson_ids = [row[0].id for row in rows]
    
    # Get booking counts for all lessons
    booking_counts = {}
    if lesson_ids:
        counts_query = (
            select(LessonBooking.lesson_id, func.count(LessonBooking.id))
            .where(
                and_(
                    LessonBooking.lesson_id.in_(lesson_ids),
                    LessonBooking.status == "booked"
                )
            )
            .group_by(LessonBooking.lesson_id)
        )
        counts_result = await session.execute(counts_query)
        booking_counts = {row[0]: row[1] for row in counts_result.fetchall()}
    
    # Get student's bookings (including excused)
    student_bookings = {}
    if lesson_ids:
        student_booking_query = (
            select(LessonBooking.lesson_id, LessonBooking.status)
            .where(
                and_(
                    LessonBooking.student_id == student_id,
                    LessonBooking.lesson_id.in_(lesson_ids),
                    LessonBooking.status.in_(["booked", "waitlist", "excused"])
                )
            )
        )
        student_booking_result = await session.execute(student_booking_query)
        student_bookings = {row[0]: row[1] for row in student_booking_result.fetchall()}
    
    sessions = []
    for row in rows:
        lesson, group, section, club, coach = row
        
        coach_name = None
        if coach:
            coach_name = f"{coach.first_name} {coach.last_name or ''}".strip()
        
        # Get booking info
        participants_count = booking_counts.get(lesson.id, 0)
        booking_status = student_bookings.get(lesson.id)
        is_booked = booking_status == "booked"
        is_in_waitlist = booking_status == "waitlist"
        is_excused = booking_status == "excused"
        
        # Determine status
        status = SessionStatus.scheduled
        if lesson.status == "cancelled":
            status = SessionStatus.cancelled
        elif is_booked:
            status = SessionStatus.booked
        elif group.capacity and participants_count >= group.capacity:
            status = SessionStatus.full
        
        sessions.append(SessionRead(
            id=lesson.id,
            section_name=section.name,
            group_name=group.name,
            coach_id=lesson.coach_id,
            coach_name=coach_name,
            club_id=club.id,
            club_name=club.name,
            club_address=club.address,
            date=lesson.planned_date,
            time=lesson.planned_start_time.strftime("%H:%M") if lesson.planned_start_time else "00:00",
            duration_minutes=lesson.duration_minutes,
            location=lesson.location,
            participants_count=participants_count,
            max_participants=group.capacity,
            status=status,
            is_booked=is_booked,
            is_in_waitlist=is_in_waitlist,
            is_excused=is_excused,
            notes=lesson.notes,
        ))
    
    return sessions, total


@db_operation
async def get_trainers_for_student(
    session: AsyncSession,
    student_id: int
) -> List[TrainerInfo]:
    """Get list of trainers from student's enrolled clubs"""
    # Get student's enrolled club IDs
    enrollment_query = (
        select(Section.club_id)
        .select_from(StudentEnrollment)
        .join(Group, StudentEnrollment.group_id == Group.id)
        .join(Section, Group.section_id == Section.id)
        .where(
            and_(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status.in_([EnrollmentStatus.active, EnrollmentStatus.new])
            )
        )
    )
    enrollment_result = await session.execute(enrollment_query)
    club_ids = list(set([row[0] for row in enrollment_result.fetchall()]))
    
    if not club_ids:
        return []
    
    # Get trainers from these clubs
    trainers_query = (
        select(UserStaff.id, UserStaff.first_name, UserStaff.last_name, Section.club_id)
        .select_from(Section)
        .join(UserStaff, Section.coach_id == UserStaff.id)
        .where(Section.club_id.in_(club_ids))
        .distinct()
    )
    
    result = await session.execute(trainers_query)
    rows = result.fetchall()
    
    trainers = []
    seen_ids = set()
    for row in rows:
        if row[0] not in seen_ids:
            seen_ids.add(row[0])
            name = f"{row[1]} {row[2] or ''}".strip()
            trainers.append(TrainerInfo(
                id=row[0],
                name=name,
                club_id=row[3]
            ))
    
    return trainers
