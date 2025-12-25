"""Lesson Booking Model - Tracks student reservations for training sessions"""
from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    ForeignKey,
    String,
    Boolean,
    Index,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.core.database import Base


class LessonBooking(Base):
    """Records of student bookings/reservations for lessons"""
    __tablename__ = "lesson_bookings"

    id = Column(Integer, primary_key=True, index=True)
    
    # Link to student
    student_id = Column(Integer, ForeignKey("user_students.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Link to lesson
    lesson_id = Column(Integer, ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Status: booked, cancelled, waitlist
    status = Column(String(20), default="booked", nullable=False, index=True)
    
    # For waitlist - position in queue
    waitlist_position = Column(Integer, nullable=True)
    
    # Flag to track if student was notified when spot opened
    notified = Column(Boolean, default=False)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    student = relationship("UserStudent", backref="lesson_bookings")
    lesson = relationship("Lesson", backref="bookings", passive_deletes=True)
    
    __table_args__ = (
        # Prevent duplicate active bookings for same student+lesson
        UniqueConstraint("student_id", "lesson_id", name="uq_lesson_booking_student_lesson"),
        Index("ix_lesson_booking_lesson_status", "lesson_id", "status"),
        Index("ix_lesson_booking_student_status", "student_id", "status"),
    )

    def __repr__(self):
        return f"<LessonBooking(id={self.id}, student_id={self.student_id}, lesson_id={self.lesson_id}, status={self.status})>"
