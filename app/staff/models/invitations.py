# app/staff/models/invitations.py
import enum
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Enum,
    Index,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.staff.models.roles import RoleType


class InvitationStatus(str, enum.Enum):
    PENDING = "pending"  # Ожидает ответа (по умолчанию)
    ACCEPTED = "accepted"  # Принято пользователем
    DECLINED = "declined"  # Отклонено пользователем
    AUTO_ACCEPTED = "auto_accepted"  # Автоматически принято при регистрации
    EXPIRED = "expired"  # Истекло по времени


class Invitation(Base):
    __tablename__ = "invitations"

    id = Column(Integer, primary_key=True)

    phone_number = Column(String(30), nullable=False, index=True)
    role = Column(Enum(RoleType), nullable=False)

    # SET NULL when club is deleted
    club_id = Column(
        Integer, ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True
    )

    # SET NULL when creator is deleted
    created_by_id = Column(
        Integer, ForeignKey("user_staff.id", ondelete="SET NULL"), nullable=True
    )

    created_by_type = Column(
        Enum("system", "superadmin", "owner", name="invitation_creator_type"),
        nullable=False,
        default="system",
    )

    # Новые поля для статуса
    status = Column(
        Enum(InvitationStatus),
        nullable=False,
        default=InvitationStatus.PENDING,
        index=True,
    )

    # SET NULL when responder is deleted
    responded_by_id = Column(
        Integer, ForeignKey("user_staff.id", ondelete="SET NULL"), nullable=True
    )

    responded_at = Column(DateTime(timezone=True), nullable=True)

    expires_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Отношения
    club = relationship("Club", foreign_keys=[club_id])
    created_by = relationship("UserStaff", foreign_keys=[created_by_id])
    responded_by = relationship("UserStaff", foreign_keys=[responded_by_id])

    # Составные индексы для оптимизации запросов
    __table_args__ = (
        # Для поиска приглашений по номеру и статусу
        Index("ix_invitations_phone_status", "phone_number", "status"),
        # Для поиска приглашений по номеру, роли и клубу
        Index("ix_invitations_phone_role_club", "phone_number", "role", "club_id"),
        # Для очистки истекших приглашений
        Index("ix_invitations_expires_status", "expires_at", "status"),
        # Для поиска по создателю
        Index("ix_invitations_creator", "created_by_id", "created_by_type"),
        # Для поиска по респонденту
        Index("ix_invitations_responder", "responded_by_id", "responded_at"),
    )

    @property
    def is_active(self) -> bool:
        """Возвращает True если приглашение активное (можно принять/отклонить)"""

        return (
            self.status == InvitationStatus.PENDING
            and self.expires_at > datetime.now(timezone.utc)
        )

    def __repr__(self):
        return f"<Invitation(id={self.id}, phone='{self.phone_number}', role={self.role}, status={self.status})>"
