"""Student Payment Model - Tracks student payments for memberships"""
from sqlalchemy import (
    Column,
    Integer,
    DateTime,
    ForeignKey,
    String,
    Numeric,
    Text,
    Date,
    Boolean,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from enum import Enum
from app.core.database import Base


class PaymentStatus(str, Enum):
    """Payment status"""
    pending = "pending"
    paid = "paid"
    failed = "failed"
    refunded = "refunded"
    cancelled = "cancelled"


class PaymentMethod(str, Enum):
    """Payment method"""
    card = "card"
    kaspi = "kaspi"
    cash = "cash"
    transfer = "transfer"


class StudentPayment(Base):
    """Records of student payments"""
    __tablename__ = "student_payments"

    id = Column(Integer, primary_key=True, index=True)
    
    # Link to student
    student_id = Column(Integer, ForeignKey("user_students.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Link to enrollment
    enrollment_id = Column(Integer, ForeignKey("student_enrollments.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Link to tariff
    tariff_id = Column(Integer, ForeignKey("tariffs.id", ondelete="SET NULL"), nullable=True)
    
    # Club context
    club_id = Column(Integer, ForeignKey("clubs.id", ondelete="SET NULL"), nullable=True, index=True)
    
    # Payment details
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="KZT", nullable=False)
    
    # Payment status
    status = Column(SQLEnum(PaymentStatus), default=PaymentStatus.pending, nullable=False)
    
    # Payment method
    payment_method = Column(SQLEnum(PaymentMethod), nullable=True)
    
    # External payment reference (e.g., from payment gateway)
    external_id = Column(String(255), nullable=True, unique=True)
    
    # Description
    description = Column(Text, nullable=True)
    
    # Payment date
    payment_date = Column(DateTime(timezone=True), nullable=True)
    
    # Flags
    is_refundable = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    student = relationship("UserStudent", backref="payments")
    club = relationship("Club", backref="student_payments")
    tariff = relationship("Tariff", backref="payments")

    def __repr__(self):
        return f"<StudentPayment(id={self.id}, student_id={self.student_id}, amount={self.amount}, status={self.status})>"
