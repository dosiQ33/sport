from pydantic import BaseModel
from typing import Literal


# если RoleType нужен в коде, можете импортировать Enum из models.roles
RoleType = Literal["coach", "manager", "admin", "owner"]


class RoleBase(BaseModel):
    code: RoleType
    name: str

    model_config = {"from_attributes": True}


class RoleCreate(RoleBase):
    pass


class RoleRead(RoleBase):
    id: int
