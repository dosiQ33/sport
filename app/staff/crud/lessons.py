from datetime import date, time
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import and_, func, or_
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import db_operation, with_db_transaction
from app.core.exceptions import (
    NotFoundError,
    ValidationError,
    PermissionDeniedError,
    BusinessLogicError,
)
from app.staff.models.lessons import Lesson
from app.staff.models.groups import Group
from app.staff.models.sections import Section
from app.staff.models.clubs import Club
from app.staff.models.users import UserStaff
from app.staff.schemas.lessons import (
    LessonCreate,
    LessonUpdate,
    LessonReschedule,
    LessonCancel,
    LessonComplete,
    LessonFilters,
)


@db_operation
async def get_lesson_by_id(session: AsyncSession, lesson_id: int) -> Lesson:
    """Get lesson by ID with related data"""
    if lesson_id <= 0:
        raise ValidationError("Lesson ID must be positive")

    result = await session.execute(
        select(Lesson)
        .options(
            selectinload(Lesson.group).selectinload(Group.section),
            selectinload(Lesson.coach),
        )
        .where(Lesson.id == lesson_id)
    )
    lesson = result.scalar_one_or_none()

    if not lesson:
        raise NotFoundError("Lesson", str(lesson_id))

    return lesson


@db_operation
async def get_lessons_paginated(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 20,
    filters: Optional[LessonFilters] = None,
) -> Tuple[List[Lesson], int]:
    """Get paginated list of lessons with filters"""
    if skip < 0:
        raise ValidationError("Skip parameter must be >= 0")

    if limit <= 0 or limit > 100:
        raise ValidationError("Limit must be between 1 and 100")

    # Base query with joins for related data
    base_query = select(Lesson).options(
        selectinload(Lesson.group).selectinload(Group.section),
        selectinload(Lesson.coach),
    )

    count_query = select(func.count(Lesson.id))

    # Apply filters
    conditions = []

    if filters:
        if filters.group_id:
            if filters.group_id <= 0:
                raise ValidationError("Group ID must be positive")
            conditions.append(Lesson.group_id == filters.group_id)

        if filters.club_id:
            if filters.club_id <= 0:
                raise ValidationError("Club ID must be positive")
            # Join with related tables to filter by club
            base_query = base_query.join(Group, Lesson.group_id == Group.id).join(
                Section, Group.section_id == Section.id
            )
            count_query = count_query.join(Group, Lesson.group_id == Group.id).join(
                Section, Group.section_id == Section.id
            )
            conditions.append(Section.club_id == filters.club_id)

        if filters.section_id:
            if filters.section_id <= 0:
                raise ValidationError("Section ID must be positive")
            base_query = base_query.join(Group, Lesson.group_id == Group.id)
            count_query = count_query.join(Group, Lesson.group_id == Group.id)
            conditions.append(Group.section_id == filters.section_id)

        if filters.coach_id:
            if filters.coach_id <= 0:
                raise ValidationError("Coach ID must be positive")
            conditions.append(Lesson.coach_id == filters.coach_id)

        if filters.date_from:
            conditions.append(Lesson.planned_date >= filters.date_from)

        if filters.date_to:
            conditions.append(Lesson.planned_date <= filters.date_to)

        if filters.status:
            conditions.append(Lesson.status == filters.status)

        if filters.location:
            conditions.append(Lesson.location.ilike(f"%{filters.location.strip()}%"))

        if filters.created_from_template is not None:
            conditions.append(
                Lesson.created_from_template == filters.created_from_template
            )

    if conditions:
        filter_condition = and_(*conditions)
        base_query = base_query.where(filter_condition)
        count_query = count_query.where(filter_condition)

    # Get total count
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    # Get paginated results
    query = (
        base_query.offset(skip)
        .limit(limit)
        .order_by(Lesson.planned_date.desc(), Lesson.planned_start_time.desc())
    )
    result = await session.execute(query)
    lessons = result.scalars().all()

    return lessons, total


@db_operation
async def get_lessons_by_date_range(
    session: AsyncSession,
    date_from: date,
    date_to: date,
    group_id: Optional[int] = None,
    coach_id: Optional[int] = None,
    include_cancelled: bool = False,
) -> List[Lesson]:
    """Get lessons in date range"""
    conditions = [
        Lesson.planned_date >= date_from,
        Lesson.planned_date <= date_to,
    ]

    if group_id:
        if group_id <= 0:
            raise ValidationError("Group ID must be positive")
        conditions.append(Lesson.group_id == group_id)

    if coach_id:
        if coach_id <= 0:
            raise ValidationError("Coach ID must be positive")
        conditions.append(Lesson.coach_id == coach_id)

    if not include_cancelled:
        conditions.append(Lesson.status != "cancelled")

    result = await session.execute(
        select(Lesson)
        .options(
            selectinload(Lesson.group).selectinload(Group.section),
            selectinload(Lesson.coach),
        )
        .where(and_(*conditions))
        .order_by(Lesson.planned_date, Lesson.planned_start_time)
    )

    return result.scalars().all()


async def create_lesson(
    session: AsyncSession, lesson: LessonCreate, user_id: int
) -> Lesson:
    """Create a new lesson with permission check"""

    async def _create_lesson_operation(session: AsyncSession):
        # Verify group exists and user has permission
        group_result = await session.execute(
            select(Group)
            .options(selectinload(Group.section))
            .where(Group.id == lesson.group_id)
        )
        group = group_result.scalar_one_or_none()
        if not group:
            raise NotFoundError("Group", str(lesson.group_id))

        # Check user permission to create lessons in this club
        from app.staff.crud.sections import check_user_club_section_permission

        permission_check = await check_user_club_section_permission(
            session, user_id, group.section.club_id
        )
        if not permission_check["can_create"]:
            raise PermissionDeniedError("create", "lesson", permission_check["reason"])

        # Verify coach if specified
        if lesson.coach_id:
            coach_result = await session.execute(
                select(UserStaff).where(UserStaff.id == lesson.coach_id)
            )
            if not coach_result.scalar_one_or_none():
                raise NotFoundError("Coach", str(lesson.coach_id))

        # Create lesson
        lesson_data = lesson.model_dump()
        lesson_data["created_from_template"] = False  # Manual creation

        db_lesson = Lesson(**lesson_data)
        session.add(db_lesson)

        return db_lesson

    # Execute in transaction
    db_lesson = await with_db_transaction(session, _create_lesson_operation)

    # Load related data
    await session.refresh(db_lesson, ["group", "coach"])
    return db_lesson


@db_operation
async def update_lesson(
    session: AsyncSession,
    lesson_id: int,
    lesson_update: LessonUpdate,
    user_id: int,
) -> Lesson:
    """Update lesson with permission check"""
    if lesson_id <= 0:
        raise ValidationError("Lesson ID must be positive")

    if user_id <= 0:
        raise ValidationError("User ID must be positive")

    # Get lesson with related data
    lesson = await get_lesson_by_id(session, lesson_id)

    # Check permission
    from app.staff.crud.sections import check_user_club_section_permission

    permission_check = await check_user_club_section_permission(
        session, user_id, lesson.group.section.club_id
    )
    if not permission_check["can_create"]:
        raise PermissionDeniedError("update", "lesson", permission_check["reason"])

    # Validate coach if being updated
    update_data = lesson_update.model_dump(exclude_unset=True)

    if "coach_id" in update_data and update_data["coach_id"]:
        coach_result = await session.execute(
            select(UserStaff).where(UserStaff.id == update_data["coach_id"])
        )
        if not coach_result.scalar_one_or_none():
            raise NotFoundError("Coach", str(update_data["coach_id"]))

    # Apply updates
    for key, value in update_data.items():
        setattr(lesson, key, value)

    await session.commit()
    await session.refresh(lesson, ["group", "coach"])

    return lesson


@db_operation
async def reschedule_lesson(
    session: AsyncSession,
    lesson_id: int,
    reschedule_data: LessonReschedule,
    user_id: int,
) -> Lesson:
    """Reschedule a lesson"""
    if lesson_id <= 0:
        raise ValidationError("Lesson ID must be positive")

    lesson = await get_lesson_by_id(session, lesson_id)

    # Check permission
    from app.staff.crud.sections import check_user_club_section_permission

    permission_check = await check_user_club_section_permission(
        session, user_id, lesson.group.section.club_id
    )
    if not permission_check["can_create"]:
        raise PermissionDeniedError("reschedule", "lesson", permission_check["reason"])

    # Validate lesson can be rescheduled
    if lesson.status == "completed":
        raise BusinessLogicError("Cannot reschedule completed lesson")

    if lesson.status == "cancelled":
        raise BusinessLogicError("Cannot reschedule cancelled lesson")

    # Update lesson
    lesson.actual_date = reschedule_data.new_date
    lesson.actual_start_time = reschedule_data.new_time
    lesson.status = "rescheduled"

    if reschedule_data.reason:
        lesson.notes = (
            f"{lesson.notes or ''}\nRescheduled: {reschedule_data.reason}".strip()
        )

    await session.commit()
    await session.refresh(lesson, ["group", "coach"])

    return lesson


@db_operation
async def cancel_lesson(
    session: AsyncSession,
    lesson_id: int,
    cancel_data: LessonCancel,
    user_id: int,
) -> Lesson:
    """Cancel a lesson"""
    if lesson_id <= 0:
        raise ValidationError("Lesson ID must be positive")

    lesson = await get_lesson_by_id(session, lesson_id)

    # Check permission
    from app.staff.crud.sections import check_user_club_section_permission

    permission_check = await check_user_club_section_permission(
        session, user_id, lesson.group.section.club_id
    )
    if not permission_check["can_create"]:
        raise PermissionDeniedError("cancel", "lesson", permission_check["reason"])

    # Validate lesson can be cancelled
    if lesson.status == "completed":
        raise BusinessLogicError("Cannot cancel completed lesson")

    if lesson.status == "cancelled":
        raise BusinessLogicError("Lesson is already cancelled")

    # Cancel lesson
    lesson.status = "cancelled"
    lesson.notes = f"{lesson.notes or ''}\nCancelled: {cancel_data.reason}".strip()

    await session.commit()
    await session.refresh(lesson, ["group", "coach"])

    return lesson


@db_operation
async def complete_lesson(
    session: AsyncSession,
    lesson_id: int,
    complete_data: LessonComplete,
    user_id: int,
) -> Lesson:
    """Mark lesson as completed"""
    if lesson_id <= 0:
        raise ValidationError("Lesson ID must be positive")

    lesson = await get_lesson_by_id(session, lesson_id)

    # Check permission (coach can complete their own lessons)
    from app.staff.crud.sections import check_user_club_section_permission

    permission_check = await check_user_club_section_permission(
        session, user_id, lesson.group.section.club_id
    )

    # Also allow the assigned coach to complete
    is_assigned_coach = lesson.coach_id == user_id

    if not (permission_check["can_create"] or is_assigned_coach):
        raise PermissionDeniedError(
            "complete", "lesson", "No permission to complete this lesson"
        )

    # Validate lesson can be completed
    if lesson.status == "cancelled":
        raise BusinessLogicError("Cannot complete cancelled lesson")

    if lesson.status == "completed":
        raise BusinessLogicError("Lesson is already completed")

    # Complete lesson
    lesson.status = "completed"

    if complete_data.notes:
        lesson.notes = f"{lesson.notes or ''}\nCompleted: {complete_data.notes}".strip()

    if complete_data.actual_duration:
        lesson.duration_minutes = complete_data.actual_duration

    await session.commit()
    await session.refresh(lesson, ["group", "coach"])

    return lesson


@db_operation
async def delete_lesson(session: AsyncSession, lesson_id: int, user_id: int) -> bool:
    """Delete a lesson"""
    if lesson_id <= 0:
        raise ValidationError("Lesson ID must be positive")

    lesson = await get_lesson_by_id(session, lesson_id)

    # Check permission
    from app.staff.crud.sections import check_user_club_section_permission

    permission_check = await check_user_club_section_permission(
        session, user_id, lesson.group.section.club_id
    )
    if not permission_check["can_create"]:
        raise PermissionDeniedError("delete", "lesson", permission_check["reason"])

    # Validate lesson can be deleted
    if lesson.status == "completed":
        raise BusinessLogicError("Cannot delete completed lesson")

    await session.delete(lesson)
    await session.commit()
    return True


@db_operation
async def get_lesson_statistics(
    session: AsyncSession,
    date_from: date,
    date_to: date,
    group_id: Optional[int] = None,
    coach_id: Optional[int] = None,
) -> Dict[str, Any]:
    """Get lesson statistics for period"""
    conditions = [
        Lesson.planned_date >= date_from,
        Lesson.planned_date <= date_to,
    ]

    if group_id:
        if group_id <= 0:
            raise ValidationError("Group ID must be positive")
        conditions.append(Lesson.group_id == group_id)

    if coach_id:
        if coach_id <= 0:
            raise ValidationError("Coach ID must be positive")
        conditions.append(Lesson.coach_id == coach_id)

    # Get statistics
    stats_result = await session.execute(
        select(
            func.count(Lesson.id).label("total_lessons"),
            func.count(Lesson.id)
            .filter(Lesson.status == "scheduled")
            .label("scheduled"),
            func.count(Lesson.id)
            .filter(Lesson.status == "completed")
            .label("completed"),
            func.count(Lesson.id)
            .filter(Lesson.status == "cancelled")
            .label("cancelled"),
            func.count(Lesson.id)
            .filter(Lesson.status == "rescheduled")
            .label("rescheduled"),
            func.avg(Lesson.duration_minutes).label("avg_duration"),
        ).where(and_(*conditions))
    )

    stats = stats_result.first()

    # Calculate rates
    total = stats.total_lessons or 0
    completion_rate = (stats.completed / total * 100) if total > 0 else 0
    cancellation_rate = (stats.cancelled / total * 100) if total > 0 else 0
    reschedule_rate = (stats.rescheduled / total * 100) if total > 0 else 0

    return {
        "total_lessons": total,
        "scheduled_lessons": stats.scheduled or 0,
        "completed_lessons": stats.completed or 0,
        "cancelled_lessons": stats.cancelled or 0,
        "rescheduled_lessons": stats.rescheduled or 0,
        "completion_rate": round(completion_rate, 2),
        "cancellation_rate": round(cancellation_rate, 2),
        "reschedule_rate": round(reschedule_rate, 2),
        "average_duration": round(stats.avg_duration or 0, 2),
        "period_start": date_from,
        "period_end": date_to,
    }


@db_operation
async def bulk_update_lessons(
    session: AsyncSession,
    lesson_ids: List[int],
    updates: LessonUpdate,
    user_id: int,
) -> Tuple[int, List[str]]:
    """Bulk update multiple lessons"""
    if not lesson_ids:
        raise ValidationError("Lesson IDs list cannot be empty")

    if len(lesson_ids) > 100:
        raise ValidationError("Cannot update more than 100 lessons at once")

    # Get all lessons
    result = await session.execute(
        select(Lesson)
        .options(selectinload(Lesson.group).selectinload(Group.section))
        .where(Lesson.id.in_(lesson_ids))
    )
    lessons = result.scalars().all()

    if not lessons:
        raise NotFoundError("Lessons", f"None of the specified lessons found")

    # Check permissions for all lessons
    errors = []
    valid_lessons = []

    for lesson in lessons:
        try:
            from app.staff.crud.sections import check_user_club_section_permission

            permission_check = await check_user_club_section_permission(
                session, user_id, lesson.group.section.club_id
            )
            if not permission_check["can_create"]:
                errors.append(f"No permission to update lesson {lesson.id}")
                continue

            # Check if lesson can be updated
            if lesson.status == "completed":
                errors.append(f"Cannot update completed lesson {lesson.id}")
                continue

            valid_lessons.append(lesson)

        except Exception as e:
            errors.append(f"Error validating lesson {lesson.id}: {str(e)}")

    # Apply updates to valid lessons
    update_data = updates.model_dump(exclude_unset=True)
    successful_updates = 0

    for lesson in valid_lessons:
        try:
            for key, value in update_data.items():
                setattr(lesson, key, value)
            successful_updates += 1
        except Exception as e:
            errors.append(f"Error updating lesson {lesson.id}: {str(e)}")

    if successful_updates > 0:
        await session.commit()

    return successful_updates, errors
