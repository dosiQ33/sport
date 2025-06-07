from sqlalchemy import (
    Column,
    Integer,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.datebase import Base


class UserRole(Base):
    """
    Таблица RBAC: одна запись = одна роль пользователя в конкретном клубе.
    Один пользователь может иметь только одну роль в одном клубе.
    """

    __tablename__ = "user_roles"

    # Add auto-increment ID as primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    club_id = Column(
        Integer, ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False
    )
    role_id = Column(
        Integer, ForeignKey("roles.id", ondelete="CASCADE"), nullable=False
    )

    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    left_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)

    # relationships
    user = relationship("UserStuff", back_populates="roles")
    club = relationship("Club", back_populates="user_roles")
    role = relationship("Role")

    __table_args__ = (
        # Ensure one user can have only one active role per club
        UniqueConstraint("user_id", "club_id", name="uq_user_club"),
        Index("ix_user_roles_user_club", "user_id", "club_id"),
        Index("ix_user_roles_active", "is_active"),
    )
