from sqlalchemy import Column, Integer, String, DateTime, JSON, BigInteger, Boolean
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class UserStaff(Base):
    __tablename__ = "user_staff"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=True)
    phone_number = Column(String(30), nullable=False)
    username = Column(String(64), nullable=True, index=True)
    preferences = Column(JSON, nullable=True, default={})
    photo_url = Column(String(256), nullable=True)

    # Добавляем поля для лимитов и суперадмина
    limits = Column(JSON, nullable=False, default={"clubs": 0, "sections": 0})

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    roles = relationship(
        "UserRole",
        back_populates="user",
        cascade="all, delete",
        lazy="select",
    )

    # Add relationships for clubs and sections
    owned_clubs = relationship(
        "Club", foreign_keys="Club.owner_id", back_populates="owner"
    )

    # Legacy: direct FK relationship (primary coach)
    primary_sections = relationship(
        "Section", foreign_keys="Section.coach_id", back_populates="coach"
    )
    
    primary_groups = relationship(
        "Group", foreign_keys="Group.coach_id", back_populates="coach"
    )
    
    # Many-to-many relationships for multiple coaches
    coached_sections = relationship(
        "SectionCoach",
        back_populates="coach",
        cascade="all, delete-orphan"
    )
    
    coached_groups = relationship(
        "GroupCoach",
        back_populates="coach",
        cascade="all, delete-orphan"
    )
