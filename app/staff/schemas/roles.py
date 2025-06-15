# app/staff/schemas/roles.py
from enum import Enum

from pydantic import BaseModel, Field


class RoleType(str, Enum):
    coach = "coach"
    admin = "admin"
    owner = "owner"


class RoleBase(BaseModel):
    code: RoleType = Field(..., description="Код роли: coach | admin | owner")
    name: str

    model_config = {
        "from_attributes": True,
        "use_enum_values": True,
    }


class RoleCreate(RoleBase):
    pass


class RoleRead(RoleBase):
    id: int
