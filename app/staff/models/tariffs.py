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


class Tariff(Base):
    __tablename__ = "tariffs"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    
    # Type: full_club, full_section, single_group, multiple_groups
    type = Column(String(50), nullable=False, default="single_group")
    
    # Payment type: monthly, semi_annual, annual, session_pack
    payment_type = Column(String(50), nullable=False, default="monthly")
    
    # Price in base currency (KZT)
    price = Column(Numeric(10, 2), nullable=False)
    
    # Access scope - stored as JSON arrays of IDs
    club_ids = Column(JSON, nullable=False, default=list)
    section_ids = Column(JSON, nullable=False, default=list)
    group_ids = Column(JSON, nullable=False, default=list)
    
    # Session pack specific fields
    sessions_count = Column(Integer, nullable=True)  # Number of sessions in pack
    validity_days = Column(Integer, nullable=True)   # Days the pack is valid
    
    # Freeze days available for this tariff (auto-migrated on startup)
    freeze_days_total = Column(Integer, nullable=False, default=0)
    
    # Features included in tariff (auto-migrated on startup)
    features = Column(JSON, nullable=False, default=list)
    
    # Status
    active = Column(Boolean, default=True, nullable=False)
    
    # Soft delete - when set, tariff is considered deleted
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Creator
    created_by_id = Column(
        Integer, ForeignKey("user_staff.id", ondelete="SET NULL"), nullable=True
    )
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    
    @property
    def is_deleted(self) -> bool:
        """Check if tariff is soft deleted"""
        return self.deleted_at is not None

    # Relations
    created_by = relationship("UserStaff", foreign_keys=[created_by_id])
    enrollments = relationship("StudentEnrollment", back_populates="tariff")

    def __repr__(self):
        return f"<Tariff(id={self.id}, name='{self.name}', type='{self.type}', price={self.price})>"
