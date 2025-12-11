"""Staff Students Schemas - For viewing and managing students from staff perspective"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
from enum import Enum


class EnrollmentStatusEnum(str, Enum):
    """Статус записи студента"""
    active = "active"
    frozen = "frozen"
    expired = "expired"
    cancelled = "cancelled"
    new = "new"


class MembershipInfo(BaseModel):
    """Информация об абонементе студента"""
    id: int
    status: EnrollmentStatusEnum
    start_date: date
    end_date: date
    tariff_id: Optional[int] = None
    tariff_name: Optional[str] = None
    price: float = 0
    freeze_days_total: int = 0
    freeze_days_used: int = 0
    freeze_start_date: Optional[date] = None
    freeze_end_date: Optional[date] = None
    
    class Config:
        from_attributes = True


class GroupInfo(BaseModel):
    """Краткая информация о группе"""
    id: int
    name: str
    section_id: int
    section_name: Optional[str] = None
    
    class Config:
        from_attributes = True


class CoachInfo(BaseModel):
    """Краткая информация о тренере"""
    id: int
    first_name: str
    last_name: Optional[str] = None
    
    class Config:
        from_attributes = True


class StudentRead(BaseModel):
    """Информация о студенте для staff приложения"""
    id: int
    telegram_id: int
    first_name: str
    last_name: Optional[str] = None
    phone_number: str
    username: Optional[str] = None
    photo_url: Optional[str] = None
    
    # Club info
    club_id: int
    club_name: str
    
    # Section/Group info
    section_id: Optional[int] = None
    section_name: Optional[str] = None
    group_id: Optional[int] = None
    group_name: Optional[str] = None
    
    # Coach info
    coach_id: Optional[int] = None
    coach_name: Optional[str] = None
    
    # Membership info
    membership: Optional[MembershipInfo] = None
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class StudentFilters(BaseModel):
    """Фильтры для списка студентов"""
    search: Optional[str] = Field(None, description="Search by name or phone")
    status: Optional[EnrollmentStatusEnum] = Field(None, description="Filter by membership status")
    club_id: Optional[int] = Field(None, description="Filter by club")
    section_id: Optional[int] = Field(None, description="Filter by section")
    group_ids: Optional[List[int]] = Field(None, description="Filter by groups")
    coach_ids: Optional[List[int]] = Field(None, description="Filter by coaches")


class StudentListResponse(BaseModel):
    """Ответ со списком студентов"""
    students: List[StudentRead]
    total: int
    page: int
    size: int
    pages: int
    filters: Optional[StudentFilters] = None


class AttendanceRecord(BaseModel):
    """Запись о посещении"""
    id: int
    date: date
    time: str
    lesson_id: int
    group_name: str
    coach_name: str
    status: str  # attended, missed, late


class PaymentRecord(BaseModel):
    """Запись о платеже"""
    id: int
    date: date
    amount: float
    operation_type: str  # purchase, extension, refund
    tariff_name: str


class StudentDetailRead(BaseModel):
    """Детальная информация о студенте"""
    id: int
    telegram_id: int
    first_name: str
    last_name: Optional[str] = None
    phone_number: str
    username: Optional[str] = None
    photo_url: Optional[str] = None
    
    # Membership info
    membership: Optional[MembershipInfo] = None
    
    # Group info
    group: Optional[GroupInfo] = None
    
    # Coach info
    coach: Optional[CoachInfo] = None
    
    # History
    attendance_history: List[AttendanceRecord] = []
    payment_history: List[PaymentRecord] = []
    
    created_at: datetime
    
    class Config:
        from_attributes = True


class ExtendMembershipRequest(BaseModel):
    """Запрос на продление абонемента"""
    enrollment_id: int
    tariff_id: int
    days: int = Field(gt=0, description="Number of days to extend")


class FreezeMembershipRequest(BaseModel):
    """Запрос на заморозку абонемента"""
    enrollment_id: int
    days: int = Field(gt=0, le=30, description="Number of days to freeze")
    reason: Optional[str] = None


class MarkAttendanceRequest(BaseModel):
    """Запрос на отметку посещения"""
    student_id: int
    lesson_id: Optional[int] = None  # If None, creates manual attendance for today
    status: str = "attended"  # attended, missed, late


class CreateEnrollmentRequest(BaseModel):
    """Запрос на создание записи студента в группу"""
    student_id: int
    group_id: int
    tariff_id: Optional[int] = None
    start_date: date
    end_date: date
    price: float = 0
    freeze_days_total: int = 0
