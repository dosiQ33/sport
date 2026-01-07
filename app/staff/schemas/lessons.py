from datetime import date, time, datetime
from typing import Any, Dict, List, Optional, Literal
from pydantic import BaseModel, Field, field_validator, ConfigDict


# Базовые схемы для занятий
class LessonBase(BaseModel):
    """Базовая схема для занятия"""

    group_id: int = Field(..., gt=0, description="Group ID")
    planned_date: date = Field(..., description="Planned lesson date")
    planned_start_time: time = Field(..., description="Planned start time")
    duration_minutes: int = Field(90, ge=30, le=300, description="Duration in minutes")
    coach_id: int = Field(..., gt=0, description="Coach ID is required")
    location: Optional[str] = Field(None, max_length=255, description="Lesson location")
    # Accept both `notes` and legacy `note` field names from various frontends
    notes: Optional[str] = Field(
        None, max_length=1000, description="Additional notes", alias="note"
    )

    model_config = ConfigDict(
        from_attributes=True, str_strip_whitespace=True, populate_by_name=True
    )


class LessonCreate(LessonBase):
    """Схема для создания занятия"""

    pass


class LessonUpdate(BaseModel):
    """Схема для обновления занятия"""

    planned_date: Optional[date] = None
    planned_start_time: Optional[time] = None
    actual_date: Optional[date] = None
    actual_start_time: Optional[time] = None
    duration_minutes: Optional[int] = Field(None, ge=30, le=300)
    status: Optional[Literal["scheduled", "completed", "cancelled", "rescheduled"]] = (
        None
    )
    coach_id: Optional[int] = Field(
        None, gt=0, description="Coach ID must be positive if provided"
    )
    location: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=1000, alias="note")

    model_config = ConfigDict(
        from_attributes=True, str_strip_whitespace=True, populate_by_name=True
    )


# Схемы для переноса/отмены занятий
class LessonReschedule(BaseModel):
    """Схема для переноса занятия"""

    new_date: date = Field(..., description="New lesson date")
    new_time: time = Field(..., description="New lesson time")
    reason: Optional[str] = Field(
        None, max_length=500, description="Reason for reschedule"
    )

    model_config = ConfigDict(from_attributes=True)


class LessonCancel(BaseModel):
    """Схема для отмены занятия"""

    reason: str = Field(
        ..., min_length=3, max_length=500, description="Reason for cancellation"
    )

    model_config = ConfigDict(from_attributes=True)


class LessonComplete(BaseModel):
    """Схема для отметки о проведении занятия"""

    notes: Optional[str] = Field(
        None, max_length=1000, description="Lesson completion notes", alias="note"
    )
    actual_duration: Optional[int] = Field(
        None, ge=15, le=300, description="Actual duration if different"
    )

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# Информационные схемы для связанных объектов
class GroupInfo(BaseModel):
    """Базовая информация о группе для занятия"""

    id: int
    name: str
    section_id: int

    model_config = ConfigDict(from_attributes=True)


class CoachInfo(BaseModel):
    """Базовая информация о тренере для занятия"""

    id: int
    first_name: str
    last_name: Optional[str] = None
    username: Optional[str] = None
    phone_number: str

    model_config = ConfigDict(from_attributes=True)


# Основная схема для чтения занятия
class LessonRead(LessonBase):
    """Схема для чтения занятия с дополнительной информацией"""

    id: int

    # Актуальные параметры (если изменились)
    actual_date: Optional[date] = None
    actual_start_time: Optional[time] = None

    status: str = "scheduled"
    created_from_template: bool = True

    created_at: datetime
    updated_at: datetime

    # Связанные объекты
    group: Optional[GroupInfo] = None
    coach: Optional[CoachInfo] = None

    # Computed properties
    effective_date: Optional[date] = None
    effective_start_time: Optional[time] = None
    is_rescheduled: bool = False

    model_config = ConfigDict(from_attributes=True)


class LessonListResponse(BaseModel):
    """Ответ со списком занятий"""

    lessons: List[LessonRead]
    total: int = Field(..., ge=0, description="Total number of lessons")
    page: int = Field(..., ge=1, description="Current page number")
    size: int = Field(..., ge=1, le=100, description="Number of items per page")
    pages: int = Field(..., ge=1, description="Total number of pages")
    filters: Optional[Dict[str, Any]] = Field(None, description="Applied filters")

    model_config = ConfigDict(from_attributes=True)


# Схемы для календарного представления
class DaySchedule(BaseModel):
    """Расписание на один день"""

    schedule_date: date
    lessons: List[LessonRead]
    total_lessons: int = 0

    model_config = ConfigDict(from_attributes=True)


class WeekSchedule(BaseModel):
    """Расписание на неделю"""

    week_start: date
    week_end: date
    days: List[DaySchedule]
    total_lessons: int = 0

    model_config = ConfigDict(from_attributes=True)


class MonthSchedule(BaseModel):
    """Расписание на месяц"""

    year: int
    month: int
    weeks: List[WeekSchedule]
    total_lessons: int = 0

    model_config = ConfigDict(from_attributes=True)


# Схемы для массовых операций
class LessonBulkUpdate(BaseModel):
    """Массовое обновление занятий"""

    lesson_ids: List[int] = Field(..., min_length=1, max_length=100)
    updates: LessonUpdate

    model_config = ConfigDict(from_attributes=True)


class LessonBulkActionResponse(BaseModel):
    """Ответ на массовые операции с занятиями"""

    message: str
    successful_updates: int
    failed_updates: int = 0
    errors: List[str] = Field(default_factory=list)
    updated_lessons: List[int] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


# Схемы для поиска и фильтрации
class LessonFilters(BaseModel):
    """Фильтры для поиска занятий"""

    group_id: Optional[int] = Field(None, gt=0)
    club_id: Optional[int] = Field(None, gt=0)
    section_id: Optional[int] = Field(None, gt=0)
    coach_id: Optional[int] = Field(None, gt=0)
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    status: Optional[Literal["scheduled", "completed", "cancelled", "rescheduled"]] = (
        None
    )
    location: Optional[str] = Field(None, max_length=255)
    created_from_template: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


# Схемы для статистики
class LessonStats(BaseModel):
    """Статистика по занятиям"""

    total_lessons: int = 0
    scheduled_lessons: int = 0
    completed_lessons: int = 0
    cancelled_lessons: int = 0
    rescheduled_lessons: int = 0

    # Процентные показатели
    completion_rate: float = Field(0.0, ge=0, le=100)
    cancellation_rate: float = Field(0.0, ge=0, le=100)
    reschedule_rate: float = Field(0.0, ge=0, le=100)

    # Период анализа
    period_start: date
    period_end: date

    model_config = ConfigDict(from_attributes=True)


class CoachLessonStats(LessonStats):
    """Статистика занятий по тренеру"""

    coach_id: int
    coach_name: str
    groups_count: int = 0  # Количество групп у тренера

    model_config = ConfigDict(from_attributes=True)


class GroupLessonStats(LessonStats):
    """Статистика занятий по группе"""

    group_id: int
    group_name: str
    section_name: str
    average_duration: float = 0.0  # Средняя продолжительность

    model_config = ConfigDict(from_attributes=True)
