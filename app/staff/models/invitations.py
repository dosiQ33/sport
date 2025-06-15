from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Enum,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.staff.models.roles import RoleType


class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(Integer, primary_key=True)
    phone_number = Column(String(30), nullable=False, unique=True, index=True)

    # Роль, которую получит пользователь
    role = Column(Enum(RoleType), nullable=False)

    # Сколько клубов может создать (0 для не-owner ролей)
    clubs_limit = Column(Integer, nullable=False, default=0)

    # Если приглашение для конкретного клуба (для admin/coach)
    # NULL для owner, обязательно для других ролей
    club_id = Column(Integer, ForeignKey("clubs.id"), nullable=True)

    # Кто создал приглашение (NULL если создано системой/superadmin)
    created_by_id = Column(Integer, ForeignKey("user_staff.id"), nullable=True)

    # Тип создателя приглашения
    created_by_type = Column(
        Enum("system", "superadmin", "owner", name="invitation_creator_type"),
        nullable=False,
        default="system",
    )

    # Статус приглашения
    is_used = Column(Boolean, default=False)

    # Временные метки
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Отношения
    club = relationship("Club", foreign_keys=[club_id])
    created_by = relationship("UserStaff", foreign_keys=[created_by_id])
