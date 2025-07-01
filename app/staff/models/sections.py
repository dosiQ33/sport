from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Boolean,
    ForeignKey,
    DateTime,
    JSON,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Section(Base):
    __tablename__ = "sections"

    id = Column(Integer, primary_key=True)
    club_id = Column(Integer, ForeignKey("clubs.id", ondelete="CASCADE"), index=True)

    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)  # Расширенное описание секции

    # Главный тренер секции (координатор)
    coach_id = Column(Integer, ForeignKey("user_staff.id"), nullable=True)

    active = Column(Boolean, default=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relations
    club = relationship("Club", back_populates="sections")
    coach = relationship("UserStaff", foreign_keys=[coach_id])
    groups = relationship("Group", back_populates="section", cascade="all, delete")

    def __repr__(self):
        return f"<Section(id={self.id}, name='{self.name}', club_id={self.club_id})>"
