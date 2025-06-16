# app/staff/models/clubs.py
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    JSON,
    ForeignKey,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Club(Base):
    __tablename__ = "clubs"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    city = Column(String(80), nullable=True)
    address = Column(String(255), nullable=True)

    logo_url = Column(String(255), nullable=True)
    cover_url = Column(String(255), nullable=True)

    phone = Column(String(32), nullable=True)
    telegram_url = Column(String(255), nullable=True)
    instagram_url = Column(String(255), nullable=True)

    # SET NULL when owner is deleted instead of CASCADE
    owner_id = Column(
        Integer, ForeignKey("user_staff.id", ondelete="SET NULL"), nullable=True
    )
    timezone = Column(String(40), default="Asia/Almaty")
    currency = Column(String(8), default="KZT")

    extra = Column(JSON, nullable=True, default={})

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # relations
    sections = relationship(
        "Section", back_populates="club", cascade="all, delete-orphan"
    )
    user_roles = relationship(
        "UserRole", back_populates="club", cascade="all, delete-orphan"
    )
    owner = relationship("UserStaff", foreign_keys=[owner_id])
