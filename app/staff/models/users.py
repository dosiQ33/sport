from sqlalchemy import Column, Integer, String, DateTime, JSON, BigInteger
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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships with CASCADE
    roles = relationship(
        "UserRole",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )

    # Clubs owned by this user
    owned_clubs = relationship(
        "Club",
        foreign_keys="Club.owner_id",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Sections coached by this user
    coached_sections = relationship(
        "Section",
        foreign_keys="Section.coach_id",
        back_populates="coach",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    # Invitations created by this user
    created_invitations = relationship(
        "Invitation",
        foreign_keys="Invitation.created_by_id",
        back_populates="created_by",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
