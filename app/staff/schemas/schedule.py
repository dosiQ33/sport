from datetime import date, time, datetime
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict

from app.core.exceptions import ValidationError


# Базовые схемы для расписания
class WeeklyTimeSlot(BaseModel):
    """Временной слот в недельном расписании"""

    time: str = Field(..., pattern=r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$")
    duration: int = Field(..., ge=30, le=300, description="Duration in minutes")

    @field_validator("time")
    @classmethod
    def validate_time_format(cls, v):
        try:
            time.fromisoformat(v)
            return v
        except ValueError:
            raise ValidationError("Invalid time format. Use HH:MM")


class WeeklySchedulePattern(BaseModel):
    """Шаблон недельного расписания"""

    monday: List[WeeklyTimeSlot] = Field(default_factory=list)
    tuesday: List[WeeklyTimeSlot] = Field(default_factory=list)
    wednesday: List[WeeklyTimeSlot] = Field(default_factory=list)
    thursday: List[WeeklyTimeSlot] = Field(default_factory=list)
    friday: List[WeeklyTimeSlot] = Field(default_factory=list)
    saturday: List[WeeklyTimeSlot] = Field(default_factory=list)
    sunday: List[WeeklyTimeSlot] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ScheduleTemplate(BaseModel):
    """Полный шаблон расписания для группы"""

    weekly_pattern: WeeklySchedulePattern
    valid_from: date = Field(..., description="Start date for this schedule")
    valid_until: date = Field(..., description="End date for this schedule")
    timezone: str = Field(default="Asia/Almaty", description="Timezone")

    model_config = ConfigDict(from_attributes=True)

    @field_validator("valid_until")
    @classmethod
    def validate_date_range(cls, v, info):
        if "valid_from" in info.data and v <= info.data["valid_from"]:
            raise ValidationError("valid_until must be after valid_from")
        return v


class ScheduleTemplateUpdate(BaseModel):
    """Схема для обновления шаблона расписания"""

    weekly_pattern: Optional[WeeklySchedulePattern] = None
    valid_from: Optional[date] = None
    valid_until: Optional[date] = None
    timezone: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# Схемы для генерации занятий
class GenerateLessonsRequest(BaseModel):
    """Запрос на генерацию занятий из шаблона"""

    start_date: date = Field(..., description="Start date for lesson generation")
    end_date: date = Field(..., description="End date for lesson generation")
    overwrite_existing: bool = Field(
        False, description="Whether to overwrite existing lessons in the date range"
    )
    exclude_holidays: bool = Field(
        True, description="Whether to exclude common holidays"
    )

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v, info):
        if "start_date" in info.data and v <= info.data["start_date"]:
            raise ValidationError("end_date must be after start_date")

        # Ограничиваем максимальный период генерации (6 месяцев)
        if "start_date" in info.data:
            days_diff = (v - info.data["start_date"]).days
            if days_diff > 180:
                raise ValidationError("Cannot generate lessons for more than 6 months")

        return v


class GenerateLessonsResponse(BaseModel):
    """Ответ на генерацию занятий"""

    message: str
    generated_count: int
    skipped_count: int = 0
    overwritten_count: int = 0
    start_date: date
    end_date: date
    group_id: int

    model_config = ConfigDict(from_attributes=True)


# Схемы для фильтров расписания
class ScheduleFilters(BaseModel):
    """Фильтры для запросов расписания"""

    group_id: Optional[int] = Field(None, gt=0)
    club_id: Optional[int] = Field(None, gt=0)
    section_id: Optional[int] = Field(None, gt=0)
    coach_id: Optional[int] = Field(None, gt=0)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    status: Optional[Literal["scheduled", "completed", "cancelled", "rescheduled"]] = (
        None
    )
    include_cancelled: bool = Field(False, description="Include cancelled lessons")

    model_config = ConfigDict(from_attributes=True)

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v, info):
        if v and "start_date" in info.data and info.data["start_date"]:
            if v < info.data["start_date"]:
                raise ValidationError("end_date must be after start_date")

            # Ограничиваем максимальный период запроса (1 год)
            days_diff = (v - info.data["start_date"]).days
            if days_diff > 365:
                raise ValidationError("Date range cannot exceed 1 year")

        return v


# Схемы для отображения расписания
class ScheduleCalendarRequest(BaseModel):
    """Запрос календарного представления расписания"""

    view_type: Literal["day", "week", "month"] = Field(default="week")
    target_date: date = Field(
        default_factory=lambda: date.today(), description="Base date for the view"
    )
    filters: ScheduleFilters = Field(default_factory=ScheduleFilters)

    model_config = ConfigDict(from_attributes=True)


# Схемы для массовых операций
class BulkScheduleAction(BaseModel):
    """Массовое действие над занятиями"""

    action: Literal["cancel", "reschedule", "change_coach"] = Field(...)
    lesson_ids: List[int] = Field(..., min_length=1, max_length=100)
    reason: Optional[str] = Field(None, max_length=500)

    # Дополнительные параметры для конкретных действий
    new_date: Optional[date] = None
    new_time: Optional[str] = None
    new_coach_id: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

    @field_validator("new_time")
    @classmethod
    def validate_time_format(cls, v):
        if v:
            try:
                time.fromisoformat(v)
                return v
            except ValueError:
                raise ValidationError("Invalid time format. Use HH:MM")
        return v


class BulkScheduleActionResponse(BaseModel):
    """Ответ на массовое действие"""

    message: str
    affected_lessons: int
    failed_lessons: int = 0
    errors: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# Схемы для статистики расписания
class ScheduleStats(BaseModel):
    """Статистика расписания"""

    group_id: int
    group_name: str
    total_lessons: int
    scheduled_lessons: int
    completed_lessons: int
    cancelled_lessons: int
    rescheduled_lessons: int
    attendance_rate: Optional[float] = None  # Будет добавлено позже

    # Статистика по датам
    period_start: date
    period_end: date

    model_config = ConfigDict(from_attributes=True)
