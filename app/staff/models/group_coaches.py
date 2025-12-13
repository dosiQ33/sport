"""Many-to-many relationship between groups and coaches"""
from sqlalchemy import (
    Column,
    Integer,
    ForeignKey,
    DateTime,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class GroupCoach(Base):
    """Association table for group-coach many-to-many relationship"""
    __tablename__ = "group_coaches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    group_id = Column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    coach_id = Column(
        Integer,
        ForeignKey("user_staff.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Whether this coach is the primary/lead coach for the group
    is_primary = Column(Boolean, default=False)
    
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    group = relationship("Group", back_populates="group_coaches")
    coach = relationship("UserStaff", back_populates="coached_groups")
    
    __table_args__ = (
        UniqueConstraint("group_id", "coach_id", name="uq_group_coach"),
    )
    
    def __repr__(self):
        return f"<GroupCoach(group_id={self.group_id}, coach_id={self.coach_id})>"
