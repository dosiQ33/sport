"""Student Booking CRUD - Operations for booking/canceling training sessions"""
from typing import List, Optional, Tuple
from datetime import date, datetime, timedelta
from sqlalchemy import and_, func
from sqlalchemy.future import select
from sqlalchemy.orm import joinedload
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
    BookSessionResponse,
    CancelBookingResponse,
    FreezeBookingResponse,
)


@db_operation
async def book_session(
    session: AsyncSession,
    student_id: int,
    lesson_id: int,
) -> BookSessionResponse:
    """
    Book a student for a training session.
    
    Validates:
    - Lesson exists and is not cancelled
    - Student has active enrollment in the lesson's group
    - Student is not already booked
    - Session is not full
    """
    # Get lesson with group info
    lesson_query = (
        select(Lesson, Group)
        .select_from(Lesson)
        .join(Group, Lesson.group_id == Group.id)
        .where(Lesson.id == lesson_id)
    )
    lesson_result = await session.execute(lesson_query)
    lesson_row = lesson_result.first()
    
    if not lesson_row:
        raise NotFoundError("Lesson", str(lesson_id))
    
    lesson, group = lesson_row
    
    # Check lesson is not cancelled
    if lesson.status == "cancelled":
        raise ValidationError("Занятие отменено")
    
    # Check lesson is in the future
    today = date.today()
    if lesson.planned_date < today:
        raise ValidationError("Нельзя записаться на прошедшее занятие")
    
    # Check if lesson is today but already started
    if lesson.planned_date == today:
        now = datetime.now().time()
        if lesson.planned_start_time and lesson.planned_start_time <= now:
            raise ValidationError("Занятие уже началось")
    
    # Check student has active enrollment in this group's club
    enrollment_query = (
        select(StudentEnrollment)
        .join(Group, StudentEnrollment.group_id == Group.id)
        .join(Section, Group.section_id == Section.id)
        .where(
            and_(
                StudentEnrollment.student_id == student_id,
                Section.club_id == (
                    select(Section.club_id)
                    .select_from(Group)
                    .join(Section, Group.section_id == Section.id)
                    .where(Group.id == lesson.group_id)
                    .scalar_subquery()
                ),
                StudentEnrollment.status.in_([EnrollmentStatus.active, EnrollmentStatus.new])
            )
        )
    )
    enrollment_result = await session.execute(enrollment_query)
    enrollment = enrollment_result.scalar_one_or_none()
    
    if not enrollment:
        raise ValidationError("У вас нет активного абонемента в этом клубе")
    
    # Check if already booked
    existing_query = select(LessonBooking).where(
        and_(
            LessonBooking.student_id == student_id,
            LessonBooking.lesson_id == lesson_id,
        )
    )
    existing_result = await session.execute(existing_query)
    existing_booking = existing_result.scalar_one_or_none()
    
    if existing_booking:
        if existing_booking.status == "booked":
            raise ValidationError("Вы уже записаны на это занятие")
        elif existing_booking.status == "waitlist":
            raise ValidationError("Вы уже в листе ожидания")
        # If cancelled, update to booked
        existing_booking.status = "booked"
        existing_booking.cancelled_at = None
        await session.commit()
        return BookSessionResponse(
            success=True,
            message="Вы успешно записались на занятие",
            booking_id=existing_booking.id
        )
    
    # Check capacity
    if group.capacity:
        booked_count_query = select(func.count()).select_from(LessonBooking).where(
            and_(
                LessonBooking.lesson_id == lesson_id,
                LessonBooking.status == "booked"
            )
        )
        count_result = await session.execute(booked_count_query)
        booked_count = count_result.scalar() or 0
        
        if booked_count >= group.capacity:
            raise ValidationError("Все места заняты")
    
    # Create booking
    booking = LessonBooking(
        student_id=student_id,
        lesson_id=lesson_id,
        status="booked",
    )
    session.add(booking)
    await session.commit()
    await session.refresh(booking)
    
    return BookSessionResponse(
        success=True,
        message="Вы успешно записались на занятие",
        booking_id=booking.id
    )


@db_operation
async def cancel_booking(
    session: AsyncSession,
    student_id: int,
    lesson_id: int,
) -> CancelBookingResponse:
    """
    Cancel a student's booking for a training session.
    
    Validates:
    - Booking exists
    - Cancellation is at least 1 hour before the session
    """
    # Get booking
    booking_query = select(LessonBooking).where(
        and_(
            LessonBooking.student_id == student_id,
            LessonBooking.lesson_id == lesson_id,
            LessonBooking.status.in_(["booked", "waitlist"])
        )
    )
    booking_result = await session.execute(booking_query)
    booking = booking_result.scalar_one_or_none()
    
    if not booking:
        raise NotFoundError("Booking", f"student={student_id}, lesson={lesson_id}")
    
    # Get lesson to check time
    lesson_query = select(Lesson).where(Lesson.id == lesson_id)
    lesson_result = await session.execute(lesson_query)
    lesson = lesson_result.scalar_one_or_none()
    
    if not lesson:
        raise NotFoundError("Lesson", str(lesson_id))
    
    # Check if cancellation is allowed (at least 1 hour before)
    lesson_datetime = datetime.combine(lesson.planned_date, lesson.planned_start_time)
    now = datetime.now()
    time_diff = lesson_datetime - now
    
    if time_diff < timedelta(hours=1):
        raise ValidationError("Отмена возможна не позднее чем за 1 час до занятия")
    
    # Cancel booking
    booking.status = "cancelled"
    booking.cancelled_at = datetime.now()
    
    await session.commit()
    
    # Check if there's someone on waitlist to notify
    waitlist_query = (
        select(LessonBooking)
        .where(
            and_(
                LessonBooking.lesson_id == lesson_id,
                LessonBooking.status == "waitlist"
            )
        )
        .order_by(LessonBooking.waitlist_position.asc())
        .limit(1)
    )
    waitlist_result = await session.execute(waitlist_query)
    next_in_waitlist = waitlist_result.scalar_one_or_none()
    
    if next_in_waitlist:
        # Move from waitlist to booked
        next_in_waitlist.status = "booked"
        next_in_waitlist.waitlist_position = None
        next_in_waitlist.notified = True  # Mark as notified
        await session.commit()
    
    return CancelBookingResponse(
        success=True,
        message="Запись на занятие отменена"
    )


@db_operation
async def freeze_booking(
    session: AsyncSession,
    student_id: int,
    lesson_id: int,
    note: Optional[str] = None,
) -> FreezeBookingResponse:
    """
    Freeze/excuse a student's booking - mark that they won't attend.
    Unlike cancellation, this keeps the spot reserved but marks absence.
    
    Validates:
    - Booking exists and is in 'booked' status
    - Can freeze until lesson starts
    """
    # Get booking
    booking_query = select(LessonBooking).where(
        and_(
            LessonBooking.student_id == student_id,
            LessonBooking.lesson_id == lesson_id,
            LessonBooking.status == "booked"
        )
    )
    booking_result = await session.execute(booking_query)
    booking = booking_result.scalar_one_or_none()
    
    if not booking:
        raise NotFoundError("Booking", f"student={student_id}, lesson={lesson_id}")
    
    # Get lesson to check time
    lesson_query = select(Lesson).where(Lesson.id == lesson_id)
    lesson_result = await session.execute(lesson_query)
    lesson = lesson_result.scalar_one_or_none()
    
    if not lesson:
        raise NotFoundError("Lesson", str(lesson_id))
    
    # Check if lesson hasn't started yet
    lesson_datetime = datetime.combine(lesson.planned_date, lesson.planned_start_time)
    now = datetime.now()
    
    if now >= lesson_datetime:
        raise ValidationError("Нельзя заморозить запись после начала занятия")
    
    # Freeze booking
    booking.status = "excused"
    booking.excuse_note = note
    booking.excused_at = datetime.now()
    
    await session.commit()
    
    return FreezeBookingResponse(
        success=True,
        message="Вы отметили, что не сможете прийти на занятие"
    )


@db_operation
async def join_waitlist(
    session: AsyncSession,
    student_id: int,
    lesson_id: int,
) -> BookSessionResponse:
    """
    Add student to waitlist for a full session.
    """
    # Check lesson exists
    lesson_query = (
        select(Lesson, Group)
        .select_from(Lesson)
        .join(Group, Lesson.group_id == Group.id)
        .where(Lesson.id == lesson_id)
    )
    lesson_result = await session.execute(lesson_query)
    lesson_row = lesson_result.first()
    
    if not lesson_row:
        raise NotFoundError("Lesson", str(lesson_id))
    
    lesson, group = lesson_row
    
    # Check lesson is not cancelled
    if lesson.status == "cancelled":
        raise ValidationError("Занятие отменено")
    
    # Check lesson is in the future
    if lesson.planned_date < date.today():
        raise ValidationError("Нельзя записаться на прошедшее занятие")
    
    # Check student has enrollment
    enrollment_query = (
        select(StudentEnrollment)
        .join(Group, StudentEnrollment.group_id == Group.id)
        .join(Section, Group.section_id == Section.id)
        .where(
            and_(
                StudentEnrollment.student_id == student_id,
                Section.club_id == (
                    select(Section.club_id)
                    .select_from(Group)
                    .join(Section, Group.section_id == Section.id)
                    .where(Group.id == lesson.group_id)
                    .scalar_subquery()
                ),
                StudentEnrollment.status.in_([EnrollmentStatus.active, EnrollmentStatus.new])
            )
        )
    )
    enrollment_result = await session.execute(enrollment_query)
    enrollment = enrollment_result.scalar_one_or_none()
    
    if not enrollment:
        raise ValidationError("У вас нет активного абонемента в этом клубе")
    
    # Check if already booked or on waitlist
    existing_query = select(LessonBooking).where(
        and_(
            LessonBooking.student_id == student_id,
            LessonBooking.lesson_id == lesson_id,
        )
    )
    existing_result = await session.execute(existing_query)
    existing = existing_result.scalar_one_or_none()
    
    if existing:
        if existing.status == "booked":
            raise ValidationError("Вы уже записаны на это занятие")
        elif existing.status == "waitlist":
            raise ValidationError("Вы уже в листе ожидания")
        # If cancelled, update to waitlist
        
    # Get current waitlist position
    max_position_query = select(func.max(LessonBooking.waitlist_position)).where(
        and_(
            LessonBooking.lesson_id == lesson_id,
            LessonBooking.status == "waitlist"
        )
    )
    max_result = await session.execute(max_position_query)
    max_position = max_result.scalar() or 0
    
    if existing:
        existing.status = "waitlist"
        existing.waitlist_position = max_position + 1
        existing.cancelled_at = None
        await session.commit()
        return BookSessionResponse(
            success=True,
            message=f"Вы добавлены в лист ожидания (позиция {max_position + 1})",
            booking_id=existing.id
        )
    
    # Create waitlist entry
    booking = LessonBooking(
        student_id=student_id,
        lesson_id=lesson_id,
        status="waitlist",
        waitlist_position=max_position + 1,
    )
    session.add(booking)
    await session.commit()
    await session.refresh(booking)
    
    return BookSessionResponse(
        success=True,
        message=f"Вы добавлены в лист ожидания (позиция {max_position + 1})",
        booking_id=booking.id
    )


@db_operation
async def get_booking_count_for_lesson(
    session: AsyncSession,
    lesson_id: int,
) -> int:
    """Get the number of confirmed bookings for a lesson."""
    count_query = select(func.count()).select_from(LessonBooking).where(
        and_(
            LessonBooking.lesson_id == lesson_id,
            LessonBooking.status == "booked"
        )
    )
    result = await session.execute(count_query)
    return result.scalar() or 0


@db_operation
async def is_student_booked_for_lesson(
    session: AsyncSession,
    student_id: int,
    lesson_id: int,
) -> Tuple[bool, bool]:
    """
    Check if student is booked or in waitlist for a lesson.
    
    Returns: (is_booked, is_in_waitlist)
    """
    booking_query = select(LessonBooking).where(
        and_(
            LessonBooking.student_id == student_id,
            LessonBooking.lesson_id == lesson_id,
        )
    )
    result = await session.execute(booking_query)
    booking = result.scalar_one_or_none()
    
    if not booking:
        return False, False
    
    return booking.status == "booked", booking.status == "waitlist"


@db_operation
async def get_lesson_participants(
    session: AsyncSession,
    lesson_id: int,
    current_student_id: int,
) -> Tuple[List[dict], List[dict], int, int, Optional[int]]:
    """
    Get list of participants for a lesson.
    
    Returns: (booked_participants, excused_participants, booked_count, excused_count, max_participants)
    """
    from app.students.models.users import UserStudent
    
    # Get lesson to get max_participants from group
    lesson_query = (
        select(Lesson, Group)
        .select_from(Lesson)
        .join(Group, Lesson.group_id == Group.id)
        .where(Lesson.id == lesson_id)
    )
    lesson_result = await session.execute(lesson_query)
    lesson_row = lesson_result.first()
    
    if not lesson_row:
        raise NotFoundError("Lesson", str(lesson_id))
    
    lesson, group = lesson_row
    max_participants = group.capacity
    
    # Get all booked and excused participants
    participants_query = (
        select(
            UserStudent.id,
            UserStudent.first_name,
            UserStudent.last_name,
            UserStudent.photo_url,
            LessonBooking.status,
            LessonBooking.excuse_note,
            LessonBooking.created_at
        )
        .select_from(LessonBooking)
        .join(UserStudent, LessonBooking.student_id == UserStudent.id)
        .where(
            and_(
                LessonBooking.lesson_id == lesson_id,
                LessonBooking.status.in_(["booked", "excused"])
            )
        )
        .order_by(LessonBooking.created_at.asc())
    )
    
    result = await session.execute(participants_query)
    rows = result.fetchall()
    
    booked_participants = []
    excused_participants = []
    
    for row in rows:
        participant = {
            "id": row[0],
            "first_name": row[1],
            "last_name": row[2],
            "photo_url": row[3],
            "is_current_user": row[0] == current_student_id,
            "status": row[4],
            "excuse_note": row[5],
        }
        
        if row[4] == "booked":
            booked_participants.append(participant)
        else:
            excused_participants.append(participant)
    
    return booked_participants, excused_participants, len(booked_participants), len(excused_participants), max_participants
