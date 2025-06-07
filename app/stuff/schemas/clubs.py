# app/schemas/clubs.py
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class ClubBase(BaseModel):
    """Общая часть, используемая в Create/Read."""

    name: str
    description: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None

    logo_url: Optional[HttpUrl] = None
    cover_url: Optional[HttpUrl] = None

    phone: Optional[str] = None
    email: Optional[str] = None
    site_url: Optional[HttpUrl] = None
    instagram_url: Optional[HttpUrl] = None

    timezone: str = "Asia/Almaty"
    currency: str = "KZT"

    extra: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)


# ---------- CRUD-схемы ----------
class ClubCreate(ClubBase):
    """POST /clubs/  — нужен только name, всё остальное опционально."""


class ClubUpdate(BaseModel):
    """PATCH /clubs/{id} — все поля опциональны."""

    name: Optional[str] = None
    description: Optional[str] = None
    city: Optional[str] = None
    address: Optional[str] = None

    logo_url: Optional[HttpUrl] = None
    cover_url: Optional[HttpUrl] = None

    phone: Optional[str] = None
    email: Optional[str] = None
    site_url: Optional[HttpUrl] = None
    instagram_url: Optional[HttpUrl] = None

    timezone: Optional[str] = None
    currency: Optional[str] = None

    extra: Optional[dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)


class ClubRead(ClubBase):
    """Ответ API."""

    id: int
    owner_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime
