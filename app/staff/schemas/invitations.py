# app/staff/schemas/invitations.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from app.core.exceptions import ValidationError
from app.core.validations import clean_phone_number
from app.staff.schemas.roles import RoleType
from app.staff.models.invitations import InvitationStatus
import re


class InvitationBase(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=20)
    role: RoleType
    club_id: Optional[int] = Field(None, gt=0)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v):
        return clean_phone_number(v)


class InvitationCreateBySuperAdmin(InvitationBase):
    """Схема для создания приглашения суперадмином"""

    pass


class InvitationCreateByOwner(BaseModel):
    """Схема для создания приглашения владельцем клуба"""

    phone_number: str = Field(..., min_length=10, max_length=30)
    role: RoleType

    @field_validator("role")
    @classmethod
    def validate_role(cls, v):
        # Owner может приглашать только admin, coach
        allowed_roles = {RoleType.admin, RoleType.coach}
        if v not in allowed_roles:
            raise ValidationError("Owner can invite only roles: admin or coach")
        return v

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v):
        clean_phone = re.sub(r"\s+", "", v)
        if not re.match(r"^\+?[1-9]\d{7,20}$", clean_phone):
            raise ValidationError("Invalid phone number format")
        return clean_phone


# Базовая информация для связанных сущностей
class ClubInfo(BaseModel):
    """Информация о клубе для ответа приглашения"""

    id: int
    name: str
    city: Optional[str] = None

    model_config = {"from_attributes": True}


class CreatorInfo(BaseModel):
    """Информация о создателе приглашения"""

    id: Optional[int] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    username: Optional[str] = None

    model_config = {"from_attributes": True}


class InvitationRead(BaseModel):
    """Схема для чтения приглашения"""

    id: int
    phone_number: str
    role: RoleType
    club_id: Optional[int] = None

    # Статус и респондент
    status: InvitationStatus
    responded_by_id: Optional[int] = None
    responded_at: Optional[datetime] = None

    # Создатель
    created_by_id: Optional[int] = None
    created_by_type: str

    # Время
    expires_at: datetime
    created_at: datetime

    # Связанные данные
    club: Optional[ClubInfo] = None
    created_by: Optional[CreatorInfo] = None
    responded_by: Optional[CreatorInfo] = None

    model_config = {"from_attributes": True}


# Новые схемы для работы с ответами на приглашения
class InvitationResponse(BaseModel):
    """Базовая схема для ответа на приглашение"""

    pass


class InvitationAccept(InvitationResponse):
    """Схема для принятия приглашения"""

    pass


class InvitationDecline(InvitationResponse):
    """Схема для отклонения приглашения"""

    reason: Optional[str] = Field(
        None, max_length=500, description="Причина отклонения (опционально)"
    )


# Ответы для списков
class InvitationListResponse(BaseModel):
    """Ответ для списка приглашений"""

    invitations: list[InvitationRead]
    total: int
    page: int
    size: int
    pages: int


class PendingInvitationRead(BaseModel):
    """Схема для ожидающих приглашений (упрощенная)"""

    id: int
    role: RoleType
    club_id: Optional[int] = None
    expires_at: datetime
    created_at: datetime

    # Информация о клубе и создателе
    club: Optional[ClubInfo] = None
    created_by: Optional[CreatorInfo] = None
    created_by_type: str

    # Дополнительная информация
    days_until_expiry: int = Field(description="Количество дней до истечения")

    model_config = {"from_attributes": True}


class PendingInvitationsResponse(BaseModel):
    """Ответ со списком ожидающих приглашений"""

    invitations: list[PendingInvitationRead]
    total: int = Field(description="Общее количество ожидающих приглашений")
    expiring_soon: int = Field(description="Количество истекающих в ближайшие 3 дня")


class InvitationActionResponse(BaseModel):
    """Ответ после действия с приглашением"""

    id: int
    status: InvitationStatus
    message: str
    club_id: Optional[int] = None
    club_name: Optional[str] = None
    role: RoleType


# Статистика приглашений
class InvitationStats(BaseModel):
    """Статистика по приглашениям"""

    total_invitations: int
    by_status: dict[str, int] = Field(description="Количество по статусам")
    by_role: dict[str, int] = Field(description="Количество по ролям")

    model_config = {"from_attributes": True}
