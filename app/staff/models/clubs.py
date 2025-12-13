from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    DateTime,
    JSON,
    ForeignKey,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base


class Club(Base):
    __tablename__ = "clubs"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)
    city = Column(String(80), nullable=True)
    address = Column(String(255), nullable=True)

    logo_url = Column(String(255), nullable=True)
    cover_url = Column(String(255), nullable=True)

    phone = Column(String(32), nullable=True)
    telegram_url = Column(String(255), nullable=True)
    instagram_url = Column(String(255), nullable=True)
    whatsapp_url = Column(String(255), nullable=True)
    
    # Working hours (e.g., "09:00-21:00" or {"mon": "09:00-21:00", "tue": "09:00-21:00", ...})
    working_hours_start = Column(String(5), nullable=True, default="09:00")
    working_hours_end = Column(String(5), nullable=True, default="21:00")
    
    # Tags for categorization
    tags = Column(JSON, nullable=True, default=list)

    owner_id = Column(Integer, ForeignKey("user_staff.id"), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # relations
    sections = relationship("Section", back_populates="club", cascade="all, delete")
    user_roles = relationship("UserRole", back_populates="club", cascade="all, delete")
    owner = relationship("UserStaff", foreign_keys=[owner_id])
    
    @property
    def working_hours(self) -> str:
        """Returns formatted working hours string"""
        start = self.working_hours_start or "09:00"
        end = self.working_hours_end or "21:00"
        return f"{start} - {end}"
