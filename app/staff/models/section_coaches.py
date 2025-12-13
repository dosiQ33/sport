"""Many-to-many relationship between sections and coaches"""
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


class SectionCoach(Base):
    """Association table for section-coach many-to-many relationship"""
    __tablename__ = "section_coaches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    
    section_id = Column(
        Integer,
        ForeignKey("sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    coach_id = Column(
        Integer,
        ForeignKey("user_staff.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Whether this coach is the primary/lead coach for the section
    is_primary = Column(Boolean, default=False)
    
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    section = relationship("Section", back_populates="section_coaches")
    coach = relationship("UserStaff", back_populates="coached_sections")
    
    __table_args__ = (
        UniqueConstraint("section_id", "coach_id", name="uq_section_coach"),
    )
    
    def __repr__(self):
        return f"<SectionCoach(section_id={self.section_id}, coach_id={self.coach_id})>"

