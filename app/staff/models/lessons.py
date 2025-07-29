from sqlalchemy import (
    Column,
    Integer,
    String,
    Date,
    Time,
    Text,
    Boolean,
    ForeignKey,
    DateTime,
    Index,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True)
    group_id = Column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    planned_date = Column(Date, nullable=False)
    planned_start_time = Column(Time, nullable=False)

    actual_date = Column(Date, nullable=True)
    actual_start_time = Column(Time, nullable=True)

    duration_minutes = Column(Integer, default=90, nullable=False)

    status = Column(
        String(20),
        default="scheduled",
        nullable=False,
        index=True,
    )

    coach_id = Column(
        Integer, ForeignKey("user_staff.id", ondelete="SET NULL"), nullable=False
    )

    location = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)

    created_from_template = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relations
    group = relationship("Group", back_populates="lessons")
    coach = relationship("UserStaff", foreign_keys=[coach_id])

    __table_args__ = (
        # Для поиска занятий группы по датам
        Index("ix_lessons_group_date", "group_id", "planned_date"),
        # Для поиска занятий тренера
        Index("ix_lessons_coach_date", "coach_id", "planned_date"),
        # Для поиска по статусу и дате
        Index("ix_lessons_status_date", "status", "planned_date"),
        # Для поиска актуальных занятий
        Index("ix_lessons_actual_date", "actual_date"),
    )

    @property
    def effective_date(self):
        """Возвращает актуальную дату (actual_date если есть, иначе planned_date)"""
        return self.actual_date if self.actual_date else self.planned_date

    @property
    def effective_start_time(self):
        """Возвращает актуальное время (actual_start_time если есть, иначе planned_start_time)"""
        return (
            self.actual_start_time
            if self.actual_start_time
            else self.planned_start_time
        )

    @property
    def is_rescheduled(self):
        """Проверяет, было ли занятие перенесено"""
        return (
            self.actual_date is not None and self.actual_date != self.planned_date
        ) or (
            self.actual_start_time is not None
            and self.actual_start_time != self.planned_start_time
        )

    def __repr__(self):
        return f"<Lesson(id={self.id}, group_id={self.group_id}, date={self.effective_date}, time={self.effective_start_time}, status={self.status})>"
