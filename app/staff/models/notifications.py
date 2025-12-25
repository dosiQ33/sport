from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Boolean, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.database import Base

class StaffNotification(Base):
    __tablename__ = "staff_notifications"

    id = Column(Integer, primary_key=True, index=True)
    recipient_id = Column(Integer, ForeignKey("user_staff.id", ondelete="CASCADE"), nullable=False, index=True)
    
    title = Column(String(255), nullable=False)
    message = Column(String(1024), nullable=False)
    
    is_read = Column(Boolean, default=False, nullable=False)
    metadata_json = Column(JSON, nullable=True, default={})  # Renamed to avoid reserved word conflict if any, though 'metadata' is usually fine in SQLA but 'metadata' attribute exists on Base.
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    recipient = relationship("UserStaff", backref="notifications")
