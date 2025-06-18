# app/staff/schemas/invitations.py
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, field_validator
from app.staff.schemas.roles import RoleType
import re


class InvitationBase(BaseModel):
    phone_number: str = Field(..., min_length=10, max_length=30)
    role: RoleType
    club_id: Optional[int] = Field(None, gt=0)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v):
        # Базовая валидация номера телефона
        clean_phone = re.sub(r"\s+", "", v)
        if not re.match(r"^\+?[1-9]\d{7,20}$", clean_phone):
            raise ValueError("Invalid phone number format")
        return clean_phone


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
            raise ValueError("Owner can invite only roles: admin or coach")
        return v

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v):
        clean_phone = re.sub(r"\s+", "", v)
        if not re.match(r"^\+?[1-9]\d{7,20}$", clean_phone):
            raise ValueError("Invalid phone number format")
        return clean_phone


class InvitationRead(InvitationBase):
    """Схема для чтения приглашения"""

    id: int
    created_by_id: Optional[int] = None
    is_used: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class InvitationListResponse(BaseModel):
    """Ответ для списка приглашений"""

    invitations: list[InvitationRead]
    total: int
    page: int
    size: int
    pages: int


class InvitationStats(BaseModel):
    """Статистика по приглашениям"""

    total_invitations: int
    used_invitations: int
    pending_invitations: int
    expired_invitations: int
    by_role: dict[str, int]
