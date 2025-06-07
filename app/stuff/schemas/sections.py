# app/schemas/sections.py
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


SectionLevel = Literal["beginner", "intermediate", "advanced", "pro"]


class SectionBase(BaseModel):
    club_id: int
    name: str

    level: Optional[SectionLevel] = None
    capacity: Optional[int] = None  # макс. мест
    price: Optional[float] = None  # базовая стоимость
    duration_min: int = 60  # длительность занятия (по умолчанию 60)

    coach_id_default: Optional[int] = None
    tags: list[str] = Field(default_factory=list)

    # JSON с расписанием (смотри пример в предыдущем ответе)
    schedule: dict[str, Any] = Field(default_factory=dict)

    active: bool = True

    model_config = ConfigDict(from_attributes=True)


# ---------- CRUD-схемы ----------
class SectionCreate(SectionBase):
    """POST /clubs/{club_id}/sections/"""


class SectionUpdate(BaseModel):
    """PATCH /sections/{id} — обновление (все поля опциональны)."""

    name: Optional[str] = None
    level: Optional[SectionLevel] = None
    capacity: Optional[int] = None
    price: Optional[float] = None
    duration_min: Optional[int] = None
    coach_id_default: Optional[int] = None
    tags: Optional[list[str]] = None
    schedule: Optional[dict[str, Any]] = None
    active: Optional[bool] = None

    model_config = ConfigDict(from_attributes=True)


class SectionRead(SectionBase):
    """Ответ API."""

    id: int
    created_at: datetime
    updated_at: datetime
