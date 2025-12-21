"""Student Enrollment Model - Links students to groups with membership info"""
from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Date,
    ForeignKey,
    Numeric,
    Boolean,
    Enum as SQLEnum,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from enum import Enum
from app.core.database import Base


class EnrollmentStatus(str, Enum):
    """Статус записи студента"""
    active = "active"          # Активный абонемент
    frozen = "frozen"          # Заморожен
    expired = "expired"        # Истек
    cancelled = "cancelled"    # Отменен
    new = "new"                # Новый (< 14 дней)
    scheduled = "scheduled"    # Запланирован (начнется после текущего абонемента)


class StudentEnrollment(Base):
    """Запись студента в группу с информацией об абонементе"""
    __tablename__ = "student_enrollments"

    id = Column(Integer, primary_key=True, index=True)
    
    # Связь со студентом (из students app)
    student_id = Column(Integer, nullable=False, index=True)
    
    # Связь с группой
    group_id = Column(Integer, ForeignKey("groups.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Информация об абонементе
    status = Column(SQLEnum(EnrollmentStatus), default=EnrollmentStatus.new, nullable=False)
    
    # Даты абонемента
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    
    # Финансовая информация
    tariff_id = Column(Integer, ForeignKey("tariffs.id", ondelete="SET NULL"), nullable=True)
    tariff_name = Column(String(100), nullable=True)
    price = Column(Numeric(10, 2), default=0)
    
    # Заморозка
    freeze_days_total = Column(Integer, default=0)  # Доступно дней заморозки
    freeze_days_used = Column(Integer, default=0)   # Использовано дней заморозки
    freeze_start_date = Column(Date, nullable=True)
    freeze_end_date = Column(Date, nullable=True)
    
    # Флаги
    is_active = Column(Boolean, default=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    group = relationship("Group", back_populates="enrollments")
    tariff = relationship("Tariff", back_populates="enrollments")
    
    def __repr__(self):
        return f"<StudentEnrollment(id={self.id}, student_id={self.student_id}, group_id={self.group_id}, status={self.status})>"
