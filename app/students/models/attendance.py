"""Student Attendance Model - Tracks student check-ins to trainings"""
from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    ForeignKey,
    String,
    Numeric,
    Text,
    Date,
    Time,
    Index,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class StudentAttendance(Base):
    """Records of student attendance/check-ins"""
    __tablename__ = "student_attendance"

    id = Column(Integer, primary_key=True, index=True)
    
    # Link to student
    student_id = Column(Integer, ForeignKey("user_students.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Link to lesson (optional - can be manual check-in)
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Link to enrollment for validation
    enrollment_id = Column(Integer, ForeignKey("student_enrollments.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Club context
    club_id = Column(Integer, ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True, index=True)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="SET NULL"), nullable=True, index=True)
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Check-in details
    checkin_date = Column(Date, nullable=False)
    checkin_time = Column(Time, nullable=True)
    
    # Location for geo-verification
    latitude = Column(Numeric(10, 8), nullable=True)
    longitude = Column(Numeric(11, 8), nullable=True)
    
    # Status: attended, missed, late, excused
    status = Column(String(20), default="attended", nullable=False)
    
    # Notes
    notes = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    student = relationship("UserStudent", backref="attendance_records")
    
    __table_args__ = (
        Index("ix_student_attendance_student_date", "student_id", "checkin_date"),
        Index("ix_student_attendance_club_date", "club_id", "checkin_date"),
    )

    def __repr__(self):
        return f"<StudentAttendance(id={self.id}, student_id={self.student_id}, date={self.checkin_date})>"
