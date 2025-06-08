import enum
from sqlalchemy import Column, Integer, String, Enum
from app.core.database import Base


class RoleType(str, enum.Enum):
    coach = "coach"
    manager = "manager"
    admin = "admin"
    owner = "owner"


class Role(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True)
    code = Column(Enum(RoleType), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=False)
