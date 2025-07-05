import math
from datetime import date, timedelta
from fastapi import APIRouter, Depends, Query, status, Request, Path
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Dict, Optional, List

from app.core.database import get_session
from app.core.limits import limiter
from app.core.dependencies import get_current_user
from app.core.exceptions import NotFoundError, ValidationError
from app.staff.schemas.schedule import (
    ScheduleTemplate,
    ScheduleTemplateUpdate,
    GenerateLessonsRequest,
    GenerateLessonsResponse,
    ScheduleFilters,
    ScheduleCalendarRequest,
    BulkScheduleAction,
    BulkScheduleActionResponse,
    ScheduleStats,
)
from app.staff.schemas.lessons import (
    LessonRead,
    LessonCreate,
    LessonUpdate,
    LessonReschedule,
    LessonCancel,
    LessonComplete,
    LessonListResponse,
    LessonFilters,
    DaySchedule,
    WeekSchedule,
    MonthSchedule,
)
from app.staff.crud.users import get_user_staff_by_telegram_id
from app.staff.crud.groups import get_group_by_id
from app.staff.crud.lessons import (
    get_lesson_by_id,
    get_lessons_paginated,
    get_lessons_by_date_range,
    create_lesson,
    update_lesson,
    reschedule_lesson,
    cancel_lesson,
    complete_lesson,
    delete_lesson,
    get_lesson_statistics,
    bulk_update_lessons,
)
from app.staff.services.schedule_generator import (
    ScheduleGenerator,
    get_week_date_range,
    get_month_date_range,
)

router = APIRouter(prefix="/schedule", tags=["Schedule & Lessons"])

# ===== SCHEDULE TEMPLATE ENDPOINTS =====


@router.get("/groups/{group_id}/template", response_model=ScheduleTemplate)
@limiter.limit("30/minute")
async def get_group_schedule_template(
    request: Request,
    group_id: int = Path(..., description="Group ID"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get schedule template for a group.

    Returns the weekly pattern and validity period for the group's schedule.
    """
    group = await get_group_by_id(db, group_id)

    if not group.schedule:
        raise NotFoundError(
            "Schedule template", f"Group {group_id} has no schedule template"
        )

    try:
        schedule_template = ScheduleTemplate(**group.schedule)
        return schedule_template
    except Exception as e:
        raise ValidationError(f"Invalid schedule template format: {str(e)}")


@router.put("/groups/{group_id}/template", response_model=ScheduleTemplate)
@limiter.limit("10/minute")
async def update_group_schedule_template(
    request: Request,
    schedule_template: ScheduleTemplate,
    group_id: int = Path(..., description="Group ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Update schedule template for a group.

    This updates the weekly pattern that will be used for generating lessons.
    Existing lessons are not affected - use regenerate endpoint to apply changes.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    from app.staff.schemas.groups import GroupUpdate

    # Method 1: Use mode='json' for proper serialization
    try:
        schedule_dict = schedule_template.model_dump(mode="json")
        group_update_data = GroupUpdate(schedule=schedule_dict)
    except Exception:
        # Method 2: Manual date conversion fallback
        schedule_dict = schedule_template.model_dump()
        # Convert date objects to strings
        if "valid_from" in schedule_dict:
            schedule_dict["valid_from"] = schedule_dict["valid_from"].isoformat()
        if "valid_until" in schedule_dict:
            schedule_dict["valid_until"] = schedule_dict["valid_until"].isoformat()
        group_update_data = GroupUpdate(schedule=schedule_dict)

    # Update the group - this will handle permission checking
    from app.staff.crud.groups import update_group

    updated_group = await update_group(db, group_id, group_update_data, user_staff.id)

    return schedule_template


@router.patch("/groups/{group_id}/template", response_model=ScheduleTemplate)
@limiter.limit("10/minute")
async def patch_group_schedule_template(
    request: Request,
    schedule_update: ScheduleTemplateUpdate,
    group_id: int = Path(..., description="Group ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Partially update schedule template for a group.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    # Get current template
    group = await get_group_by_id(db, group_id)

    if not group.schedule:
        raise NotFoundError(
            "Schedule template", f"Group {group_id} has no schedule template"
        )

    try:
        current_template = ScheduleTemplate(**group.schedule)
    except Exception as e:
        raise ValidationError(f"Invalid current schedule template: {str(e)}")

    # Apply partial updates
    update_data = schedule_update.model_dump(exclude_unset=True)
    updated_template_data = current_template.model_dump()
    updated_template_data.update(update_data)

    updated_template = ScheduleTemplate(**updated_template_data)

    # Update group with proper serialization
    from app.staff.schemas.groups import GroupUpdate

    try:
        schedule_dict = updated_template.model_dump(mode="json")
        group_update_data = GroupUpdate(schedule=schedule_dict)
    except Exception:
        # Fallback with manual date conversion
        schedule_dict = updated_template.model_dump()
        if "valid_from" in schedule_dict:
            schedule_dict["valid_from"] = schedule_dict["valid_from"].isoformat()
        if "valid_until" in schedule_dict:
            schedule_dict["valid_until"] = schedule_dict["valid_until"].isoformat()
        group_update_data = GroupUpdate(schedule=schedule_dict)

    from app.staff.crud.groups import update_group

    await update_group(db, group_id, group_update_data, user_staff.id)

    return updated_template


# ===== LESSON GENERATION ENDPOINTS =====


@router.post(
    "/groups/{group_id}/generate-lessons", response_model=GenerateLessonsResponse
)
@limiter.limit("5/minute")
async def generate_lessons_from_template(
    request: Request,
    generation_request: GenerateLessonsRequest,
    group_id: int = Path(..., description="Group ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Generate lessons from group's schedule template.

    Creates individual lesson records based on the weekly pattern.
    Can be used to extend the schedule or fill gaps.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    # Check permissions by trying to get the group
    await get_group_by_id(db, group_id)

    # Generate lessons
    generator = ScheduleGenerator(db)
    generated_count, skipped_count, overwritten_count = (
        await generator.generate_lessons_from_template(group_id, generation_request)
    )

    return GenerateLessonsResponse(
        message=f"Successfully generated {generated_count} lessons",
        generated_count=generated_count,
        skipped_count=skipped_count,
        overwritten_count=overwritten_count,
        start_date=generation_request.start_date,
        end_date=generation_request.end_date,
        group_id=group_id,
    )


@router.post(
    "/groups/{group_id}/regenerate-lessons", response_model=GenerateLessonsResponse
)
@limiter.limit("3/minute")
async def regenerate_lessons_for_period(
    request: Request,
    start_date: date = Query(..., description="Start date for regeneration"),
    end_date: date = Query(..., description="End date for regeneration"),
    preserve_modifications: bool = Query(True, description="Preserve modified lessons"),
    group_id: int = Path(..., description="Group ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Regenerate lessons for a period, applying updated template.

    Useful when the schedule template has changed and you want to apply
    changes to future lessons while preserving manual modifications.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    # Validate date range
    if end_date <= start_date:
        raise ValidationError("End date must be after start date")

    if (end_date - start_date).days > 180:
        raise ValidationError("Cannot regenerate more than 6 months at once")

    # Check permissions
    await get_group_by_id(db, group_id)

    # Regenerate lessons
    generator = ScheduleGenerator(db)
    generated_count, preserved_count = await generator.regenerate_lessons_for_period(
        group_id, start_date, end_date, preserve_modifications
    )

    return GenerateLessonsResponse(
        message=f"Regenerated {generated_count} lessons, preserved {preserved_count} modifications",
        generated_count=generated_count,
        skipped_count=preserved_count,
        overwritten_count=0,
        start_date=start_date,
        end_date=end_date,
        group_id=group_id,
    )


# ===== INDIVIDUAL LESSON MANAGEMENT =====


@router.post("/lessons", response_model=LessonRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("10/minute")
async def create_manual_lesson(
    request: Request,
    lesson: LessonCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Create a manual lesson (not from template).

    Useful for one-off lessons, makeup classes, or special events.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    db_lesson = await create_lesson(db, lesson, user_staff.id)
    return db_lesson


@router.get("/lessons/{lesson_id}", response_model=LessonRead)
@limiter.limit("30/minute")
async def get_lesson(
    request: Request,
    lesson_id: int = Path(..., description="Lesson ID"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get lesson details by ID.
    """
    lesson = await get_lesson_by_id(db, lesson_id)
    return lesson


@router.put("/lessons/{lesson_id}", response_model=LessonRead)
@limiter.limit("10/minute")
async def update_lesson_details(
    request: Request,
    lesson_update: LessonUpdate,
    lesson_id: int = Path(..., description="Lesson ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Update lesson details.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    db_lesson = await update_lesson(db, lesson_id, lesson_update, user_staff.id)
    return db_lesson


@router.post("/lessons/{lesson_id}/reschedule", response_model=LessonRead)
@limiter.limit("10/minute")
async def reschedule_lesson_endpoint(
    request: Request,
    reschedule_data: LessonReschedule,
    lesson_id: int = Path(..., description="Lesson ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Reschedule a lesson to a different date/time.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    db_lesson = await reschedule_lesson(db, lesson_id, reschedule_data, user_staff.id)
    return db_lesson


@router.post("/lessons/{lesson_id}/cancel", response_model=LessonRead)
@limiter.limit("10/minute")
async def cancel_lesson_endpoint(
    request: Request,
    cancel_data: LessonCancel,
    lesson_id: int = Path(..., description="Lesson ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Cancel a lesson.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    db_lesson = await cancel_lesson(db, lesson_id, cancel_data, user_staff.id)
    return db_lesson


@router.post("/lessons/{lesson_id}/complete", response_model=LessonRead)
@limiter.limit("20/minute")
async def complete_lesson_endpoint(
    request: Request,
    complete_data: LessonComplete,
    lesson_id: int = Path(..., description="Lesson ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Mark lesson as completed.

    Coaches can mark their own lessons as completed.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    db_lesson = await complete_lesson(db, lesson_id, complete_data, user_staff.id)
    return db_lesson


@router.delete("/lessons/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/minute")
async def delete_lesson_endpoint(
    request: Request,
    lesson_id: int = Path(..., description="Lesson ID"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Delete a lesson.

    ⚠️ **Warning**: Cannot delete completed lessons.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    await delete_lesson(db, lesson_id, user_staff.id)


# ===== SCHEDULE VIEWING ENDPOINTS =====


@router.get("/lessons", response_model=LessonListResponse)
@limiter.limit("30/minute")
async def get_lessons_list(
    request: Request,
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    size: int = Query(20, ge=1, le=100, description="Number of items per page"),
    # Filters
    group_id: Optional[int] = Query(None, gt=0, description="Filter by group"),
    club_id: Optional[int] = Query(None, gt=0, description="Filter by club"),
    section_id: Optional[int] = Query(None, gt=0, description="Filter by section"),
    coach_id: Optional[int] = Query(None, gt=0, description="Filter by coach"),
    date_from: Optional[date] = Query(None, description="Start date filter"),
    date_to: Optional[date] = Query(None, description="End date filter"),
    status: Optional[str] = Query(None, description="Filter by status"),
    location: Optional[str] = Query(None, description="Filter by location"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get paginated list of lessons with filters.
    """
    skip = (page - 1) * size

    filters = LessonFilters(
        group_id=group_id,
        club_id=club_id,
        section_id=section_id,
        coach_id=coach_id,
        date_from=date_from,
        date_to=date_to,
        status=status,
        location=location,
    )

    lessons, total = await get_lessons_paginated(
        db, skip=skip, limit=size, filters=filters
    )

    pages = math.ceil(total / size) if total > 0 else 1

    # Applied filters
    applied_filters = {}
    for field, value in filters.model_dump().items():
        if value is not None:
            applied_filters[field] = value

    return LessonListResponse(
        lessons=lessons,
        total=total,
        page=page,
        size=size,
        pages=pages,
        filters=applied_filters if applied_filters else None,
    )


@router.get("/calendar/day/{target_date}", response_model=DaySchedule)
@limiter.limit("60/minute")
async def get_day_schedule(
    request: Request,
    target_date: date = Path(..., description="Target date"),
    group_id: Optional[int] = Query(None, gt=0, description="Filter by group"),
    coach_id: Optional[int] = Query(None, gt=0, description="Filter by coach"),
    club_id: Optional[int] = Query(None, gt=0, description="Filter by club"),
    include_cancelled: bool = Query(False, description="Include cancelled lessons"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get schedule for a specific day.
    """
    lessons = await get_lessons_by_date_range(
        db,
        date_from=target_date,
        date_to=target_date,
        group_id=group_id,
        coach_id=coach_id,
        include_cancelled=include_cancelled,
    )

    # Filter by club if needed
    if club_id:
        lessons = [
            lesson for lesson in lessons if lesson.group.section.club_id == club_id
        ]

    return DaySchedule(
        schedule_date=target_date,
        lessons=lessons,
        total_lessons=len(lessons),
    )


@router.get("/calendar/week/{target_date}", response_model=WeekSchedule)
@limiter.limit("60/minute")
async def get_week_schedule(
    request: Request,
    target_date: date = Path(..., description="Any date in target week"),
    group_id: Optional[int] = Query(None, gt=0, description="Filter by group"),
    coach_id: Optional[int] = Query(None, gt=0, description="Filter by coach"),
    club_id: Optional[int] = Query(None, gt=0, description="Filter by club"),
    include_cancelled: bool = Query(False, description="Include cancelled lessons"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get schedule for a week containing the target date.
    """
    week_start, week_end = get_week_date_range(target_date)

    lessons = await get_lessons_by_date_range(
        db,
        date_from=week_start,
        date_to=week_end,
        group_id=group_id,
        coach_id=coach_id,
        include_cancelled=include_cancelled,
    )

    # Filter by club if needed
    if club_id:
        lessons = [
            lesson for lesson in lessons if lesson.group.section.club_id == club_id
        ]

    # Group lessons by day
    lessons_by_date = {}
    for lesson in lessons:
        lesson_date = lesson.planned_date
        if lesson_date not in lessons_by_date:
            lessons_by_date[lesson_date] = []
        lessons_by_date[lesson_date].append(lesson)

    # Create day schedules
    days = []
    current_date = week_start
    while current_date <= week_end:
        day_lessons = lessons_by_date.get(current_date, [])
        days.append(
            DaySchedule(
                schedule_date=current_date,
                lessons=day_lessons,
                total_lessons=len(day_lessons),
            )
        )
        current_date += timedelta(days=1)

    return WeekSchedule(
        week_start=week_start,
        week_end=week_end,
        days=days,
        total_lessons=len(lessons),
    )


@router.get("/stats/group/{group_id}")
@limiter.limit("20/minute")
async def get_group_schedule_stats(
    request: Request,
    group_id: int = Path(..., description="Group ID"),
    date_from: date = Query(..., description="Start date for statistics"),
    date_to: date = Query(..., description="End date for statistics"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get schedule statistics for a group.
    """
    # Validate date range
    if date_to <= date_from:
        raise ValidationError("End date must be after start date")

    if (date_to - date_from).days > 365:
        raise ValidationError("Statistics period cannot exceed 1 year")

    stats = await get_lesson_statistics(db, date_from, date_to, group_id=group_id)

    # Get group info
    group = await get_group_by_id(db, group_id)

    return {
        "group_id": group_id,
        "group_name": group.name,
        **stats,
    }


@router.get("/stats/coach/{coach_id}")
@limiter.limit("20/minute")
async def get_coach_schedule_stats(
    request: Request,
    coach_id: int = Path(..., description="Coach ID"),
    date_from: date = Query(..., description="Start date for statistics"),
    date_to: date = Query(..., description="End date for statistics"),
    db: AsyncSession = Depends(get_session),
):
    """
    Get schedule statistics for a coach.
    """
    # Validate date range
    if date_to <= date_from:
        raise ValidationError("End date must be after start date")

    if (date_to - date_from).days > 365:
        raise ValidationError("Statistics period cannot exceed 1 year")

    stats = await get_lesson_statistics(db, date_from, date_to, coach_id=coach_id)

    return {
        "coach_id": coach_id,
        **stats,
    }


@router.post("/lessons/bulk-update", response_model=Dict[str, Any])
@limiter.limit("5/minute")
async def bulk_update_lessons_endpoint(
    request: Request,
    lesson_ids: List[int] = Query(..., description="List of lesson IDs to update"),
    updates: LessonUpdate = ...,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """
    Bulk update multiple lessons.

    Limited to 100 lessons per request.
    """
    user_staff = await get_user_staff_by_telegram_id(db, current_user.get("id"))
    if not user_staff:
        raise NotFoundError("Staff user")

    successful_updates, errors = await bulk_update_lessons(
        db, lesson_ids, updates, user_staff.id
    )

    return {
        "message": f"Updated {successful_updates} lessons",
        "successful_updates": successful_updates,
        "failed_updates": len(errors),
        "errors": errors,
    }
