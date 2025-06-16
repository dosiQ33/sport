from pydantic import BaseModel
from datetime import datetime
from typing import Literal


RoleType = Literal["student", "coach", "admin", "owner"]


class UserRoleBase(BaseModel):
    user_id: int
    club_id: int
    role_code: RoleType

    model_config = {"from_attributes": True}


class UserRoleCreate(UserRoleBase):
    """
    При создании передаём role_code; в сервис-слое ищем Role.id
    и создаём запись UserRole.
    """

    pass


class UserRoleRead(UserRoleBase):
    joined_at: datetime
    left_at: datetime | None = None
    is_active: bool
