from sqlalchemy import Column, Integer, String, DateTime, JSON, BigInteger
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.core.datebase import Base


class UserStuff(Base):
    __tablename__ = "user_stuff"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, unique=True, index=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=True)
    phone_number = Column(String(30), nullable=False)
    username = Column(String(64), nullable=True, index=True)
    preferences = Column(JSON, nullable=True, default={})
    photo_url = Column(String(256), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    roles = relationship(
        "UserRole",
        back_populates="user",
        cascade="all, delete",
        lazy="select",
    )
