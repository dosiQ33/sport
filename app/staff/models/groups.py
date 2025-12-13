from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    ForeignKey,
    Numeric,
    DateTime,
    JSON,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    section_id = Column(
        Integer,
        ForeignKey("sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    coach_id = Column(
        Integer, ForeignKey("user_staff.id", ondelete="SET NULL"), nullable=False
    )

    # Данные перенесенные из sections
    schedule = Column(JSON, nullable=True, default=dict)
    price = Column(Numeric(10, 2), nullable=True)
    capacity = Column(Integer, nullable=True)
    level = Column(String(20), nullable=True)

    # Дополнительные поля
    tags = Column(JSON, nullable=True, default=list)
    active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relations
    section = relationship("Section", back_populates="groups")
    # Primary coach (legacy FK relationship)
    coach = relationship("UserStaff", foreign_keys=[coach_id], back_populates="primary_groups")
    lessons = relationship("Lesson", back_populates="group", cascade="all, delete")
    enrollments = relationship("StudentEnrollment", back_populates="group", cascade="all, delete")
    # Multiple coaches relationship
    group_coaches = relationship(
        "GroupCoach",
        back_populates="group",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return (
            f"<Group(id={self.id}, name='{self.name}', section_id={self.section_id})>"
        )
