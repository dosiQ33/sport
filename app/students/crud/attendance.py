"""Student Attendance CRUD - Operations for check-in and attendance tracking"""
import math
from typing import List, Tuple, Optional
from datetime import date, datetime, timedelta
from sqlalchemy import and_, or_, func, extract
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db_operation
from app.core.exceptions import NotFoundError, ValidationError
from app.students.models.attendance import StudentAttendance
from app.students.models.users import UserStudent
from app.staff.models.enrollments import StudentEnrollment, EnrollmentStatus
from app.staff.models.groups import Group
from app.staff.models.sections import Section
from app.staff.models.clubs import Club
from app.staff.models.users import UserStaff
from app.staff.models.lessons import Lesson
from app.students.schemas.attendance import (
    CheckInRequest,
    CheckInResponse,
    AttendanceRecordRead,
    AttendanceStatsResponse,
    AttendanceStatus,
)


@db_operation
async def check_in_student(
    session: AsyncSession,
    student_id: int,
    request: CheckInRequest
) -> CheckInResponse:
    """Record a student check-in"""
    # Get student's active memberships to find which club/section to check into
    enrollment_query = (
        select(StudentEnrollment, Group, Section, Club)
        .select_from(StudentEnrollment)
        .join(Group, StudentEnrollment.group_id == Group.id)
        .join(Section, Group.section_id == Section.id)
        .join(Club, Section.club_id == Club.id)
        .where(
            and_(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.status.in_([EnrollmentStatus.active, EnrollmentStatus.new])
            )
        )
    )
    
    result = await session.execute(enrollment_query)
    enrollments = result.fetchall()
    
    if not enrollments:
        return CheckInResponse(
            success=False,
            message="No active membership found"
        )
    
    # Use first active enrollment for check-in
    enrollment, group, section, club = enrollments[0]
    
    # Check for existing check-in today
    today = date.today()
    existing_query = (
        select(StudentAttendance)
        .where(
            and_(
                StudentAttendance.student_id == student_id,
                StudentAttendance.checkin_date == today,
                StudentAttendance.club_id == club.id
            )
        )
    )
    existing_result = await session.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        return CheckInResponse(
            success=False,
            message="Already checked in today",
            attendance_id=existing.id,
            checkin_time=existing.created_at,
            club_name=club.name,
            section_name=section.name
        )
    
    # Create attendance record
    now = datetime.now()
    attendance = StudentAttendance(
        student_id=student_id,
        enrollment_id=enrollment.id,
        club_id=club.id,
        section_id=section.id,
        group_id=group.id,
        lesson_id=request.lesson_id,
        checkin_date=today,
        checkin_time=now.time(),
        latitude=request.latitude,
        longitude=request.longitude,
        status="attended"
    )
    
    session.add(attendance)
    await session.commit()
    await session.refresh(attendance)
    
    return CheckInResponse(
        success=True,
        message="Check-in successful",
        attendance_id=attendance.id,
        checkin_time=attendance.created_at,
        club_name=club.name,
        section_name=section.name
    )


@db_operation
async def get_student_attendance(
    session: AsyncSession,
    student_id: int,
    skip: int = 0,
    limit: int = 20,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None
) -> Tuple[List[AttendanceRecordRead], int]:
    """Get student attendance records"""
    base_query = (
        select(
            StudentAttendance,
            Club,
            Section,
            Group,
            Lesson,
            UserStaff
        )
        .select_from(StudentAttendance)
        .outerjoin(Club, StudentAttendance.club_id == Club.id)
        .outerjoin(Section, StudentAttendance.section_id == Section.id)
        .outerjoin(Group, StudentAttendance.group_id == Group.id)
        .outerjoin(Lesson, StudentAttendance.lesson_id == Lesson.id)
        .outerjoin(UserStaff, Lesson.coach_id == UserStaff.id)
        .where(StudentAttendance.student_id == student_id)
    )
    
    if date_from:
        base_query = base_query.where(StudentAttendance.checkin_date >= date_from)
    if date_to:
        base_query = base_query.where(StudentAttendance.checkin_date <= date_to)
    
    # Count
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0
    
    # Get paginated results
    query = base_query.order_by(StudentAttendance.checkin_date.desc()).offset(skip).limit(limit)
    result = await session.execute(query)
    rows = result.fetchall()
    
    records = []
    for row in rows:
        attendance, club, section, group, lesson, coach = row
        
        coach_name = None
        if coach:
            coach_name = f"{coach.first_name} {coach.last_name or ''}".strip()
        
        lesson_time = None
        if lesson:
            lesson_time = lesson.planned_start_time.strftime("%H:%M") if lesson.planned_start_time else None
        
        records.append(AttendanceRecordRead(
            id=attendance.id,
            club_id=attendance.club_id,
            club_name=club.name if club else None,
            section_id=attendance.section_id,
            section_name=section.name if section else None,
            group_id=attendance.group_id,
            group_name=group.name if group else None,
            checkin_date=attendance.checkin_date,
            checkin_time=attendance.checkin_time,
            status=AttendanceStatus(attendance.status),
            lesson_id=attendance.lesson_id,
            lesson_time=lesson_time,
            coach_name=coach_name,
            notes=attendance.notes,
            created_at=attendance.created_at,
        ))
    
    return records, total


@db_operation
async def get_attendance_stats(
    session: AsyncSession,
    student_id: int
) -> AttendanceStatsResponse:
    """Get attendance statistics for a student"""
    today = date.today()
    month_start = today.replace(day=1)
    
    # Visits this month
    visits_query = (
        select(func.count(StudentAttendance.id))
        .where(
            and_(
                StudentAttendance.student_id == student_id,
                StudentAttendance.checkin_date >= month_start,
                StudentAttendance.status == "attended"
            )
        )
    )
    visits_result = await session.execute(visits_query)
    visits_this_month = visits_result.scalar() or 0
    
    # Total visits
    total_query = (
        select(func.count(StudentAttendance.id))
        .where(
            and_(
                StudentAttendance.student_id == student_id,
                StudentAttendance.status == "attended"
            )
        )
    )
    total_result = await session.execute(total_query)
    total_visits = total_result.scalar() or 0
    
    # Missed this month (lessons where student was enrolled but didn't attend)
    # For simplicity, we count missed as 0 for now - can be enhanced later
    missed_this_month = 0
    
    # Calculate average attendance (visits / total days in membership)
    # For now, use a simple calculation
    average_attendance = 0.0
    if total_visits > 0:
        # Get first attendance date
        first_query = (
            select(StudentAttendance.checkin_date)
            .where(StudentAttendance.student_id == student_id)
            .order_by(StudentAttendance.checkin_date.asc())
            .limit(1)
        )
        first_result = await session.execute(first_query)
        first_date = first_result.scalar()
        
        if first_date:
            days_since_first = (today - first_date).days + 1
            if days_since_first > 0:
                average_attendance = round((total_visits / days_since_first) * 100, 1)
    
    # Last visit
    last_query = (
        select(StudentAttendance.checkin_date)
        .where(
            and_(
                StudentAttendance.student_id == student_id,
                StudentAttendance.status == "attended"
            )
        )
        .order_by(StudentAttendance.checkin_date.desc())
        .limit(1)
    )
    last_result = await session.execute(last_query)
    last_visit_date = last_result.scalar()
    
    # Calculate streak
    streak_days = 0
    if last_visit_date:
        current_date = today
        while True:
            check_query = (
                select(func.count(StudentAttendance.id))
                .where(
                    and_(
                        StudentAttendance.student_id == student_id,
                        StudentAttendance.checkin_date == current_date,
                        StudentAttendance.status == "attended"
                    )
                )
            )
            check_result = await session.execute(check_query)
            if check_result.scalar() > 0:
                streak_days += 1
                current_date -= timedelta(days=1)
            else:
                break
    
    return AttendanceStatsResponse(
        visits_this_month=visits_this_month,
        missed_this_month=missed_this_month,
        average_attendance=average_attendance,
        total_visits=total_visits,
        streak_days=streak_days,
        last_visit_date=last_visit_date
    )
