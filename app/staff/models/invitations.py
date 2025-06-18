# app/staff/models/invitations.py
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

    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Отношения
    club = relationship("Club", foreign_keys=[club_id])
    created_by = relationship("UserStaff", foreign_keys=[created_by_id])
