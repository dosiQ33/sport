from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy import and_, func, or_
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.staff.models.invitations import Invitation
from app.staff.models.users import UserStaff
from app.staff.models.clubs import Club
from app.staff.models.roles import RoleType
from app.staff.schemas.invitations import (
    InvitationCreateBySuperAdmin,
    InvitationCreateByOwner,
)


async def get_invitation_by_phone(
    session: AsyncSession, phone_number: str
) -> Optional[Invitation]:
    """Получить активное приглашение по номеру телефона"""
    result = await session.execute(
        select(Invitation)
        .options(
            selectinload(Invitation.club),
            selectinload(Invitation.created_by),
        )
        .where(
            and_(
                Invitation.phone_number == phone_number,
                Invitation.is_used == False,
            )
        )
    )
    return result.scalar_one_or_none()


async def get_invitation_by_id(
    session: AsyncSession, invitation_id: int
) -> Optional[Invitation]:
    """Получить приглашение по ID"""
    result = await session.execute(
        select(Invitation)
        .options(
            selectinload(Invitation.club),
            selectinload(Invitation.created_by),
        )
        .where(Invitation.id == invitation_id)
    )
    return result.scalar_one_or_none()


async def create_invitation_by_superadmin(
    session: AsyncSession,
    invitation_data: InvitationCreateBySuperAdmin,
    created_by_type: str = "superadmin",
) -> Invitation:
    """Создать приглашение от суперадмина"""

    # Проверяем, что не существует активного приглашения для этого номера
    existing = await get_invitation_by_phone(session, invitation_data.phone_number)
    if existing:
        raise ValueError(
            f"Active invitation for {invitation_data.phone_number} already exists"
        )

    # Для owner приглашений club_id должен быть NULL
    if invitation_data.role == RoleType.owner and invitation_data.club_id:
        raise ValueError("Owner invitations should not have club_id")

    db_invitation = Invitation(
        **invitation_data.model_dump(),
        created_by_id=None,  # SuperAdmin не в базе
        created_by_type=created_by_type,
    )

    session.add(db_invitation)
    await session.commit()
    await session.refresh(db_invitation)

    # Загружаем связанные данные (created_by будет None для superadmin)
    await session.refresh(db_invitation, ["club"])

    return db_invitation


async def create_invitation_by_owner(
    session: AsyncSession,
    invitation_data: InvitationCreateByOwner,
    owner_id: int,
    club_id: int,
) -> Invitation:
    """Создать приглашение от владельца клуба"""

    # Проверяем, что не существует активного приглашения для этого номера
    existing = await get_invitation_by_phone(session, invitation_data.phone_number)
    if existing:
        raise ValueError(
            f"Active invitation for {invitation_data.phone_number} already exists"
        )

    # Проверяем, что клуб существует и принадлежит owner
    club_result = await session.execute(
        select(Club).where(and_(Club.id == club_id, Club.owner_id == owner_id))
    )
    club = club_result.scalar_one_or_none()
    if not club:
        raise ValueError("Club not found or you don't own it")

    # Не-owner роли ДОЛЖНЫ иметь club_id
    if invitation_data.role == RoleType.owner:
        raise ValueError("Owners cannot invite other owners")

    db_invitation = Invitation(
        phone_number=invitation_data.phone_number,
        role=invitation_data.role,
        club_id=club_id,
        created_by_id=owner_id,
        created_by_type="owner",
    )

    session.add(db_invitation)
    await session.commit()
    await session.refresh(db_invitation)

    # Загружаем связанные данные
    await session.refresh(db_invitation, ["club", "created_by"])

    return db_invitation


async def mark_invitation_as_used(
    session: AsyncSession, invitation_id: int, user_id: int
) -> bool:
    """Пометить приглашение как использованное"""
    invitation = await get_invitation_by_id(session, invitation_id)
    if not invitation:
        return False

    invitation.is_used = True

    await session.commit()
    return True


async def get_invitations_paginated(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    created_by_id: Optional[int] = None,
    club_id: Optional[int] = None,
    is_used: Optional[bool] = None,
    role: Optional[RoleType] = None,
):
    """Получить список приглашений с пагинацией"""
    base_query = select(Invitation).options(
        selectinload(Invitation.club),
        selectinload(Invitation.created_by),
    )
    count_query = select(func.count(Invitation.id))

    conditions = []

    if created_by_id is not None:
        conditions.append(Invitation.created_by_id == created_by_id)
    if club_id is not None:
        conditions.append(Invitation.club_id == club_id)
    if is_used is not None:
        conditions.append(Invitation.is_used == is_used)
    if role is not None:
        conditions.append(Invitation.role == role)

    if conditions:
        filter_condition = and_(*conditions)
        base_query = base_query.where(filter_condition)
        count_query = count_query.where(filter_condition)

    # Получаем общее количество
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    # Получаем пагинированные результаты
    query = base_query.offset(skip).limit(limit).order_by(Invitation.created_at.desc())
    result = await session.execute(query)
    invitations = result.scalars().all()

    return invitations, total


async def delete_invitation(
    session: AsyncSession, invitation_id: int, deleter_id: int
) -> bool:
    """Удалить приглашение"""
    invitation = await get_invitation_by_id(session, invitation_id)
    if not invitation:
        return False

    # Проверяем права на удаление
    deleter = await session.get(UserStaff, deleter_id)
    if not deleter.is_superadmin and invitation.created_by_id != deleter_id:
        raise PermissionError("You can only delete invitations you created")

    # Нельзя удалять использованные приглашения
    if invitation.is_used:
        raise ValueError("Cannot delete used invitation")

    await session.delete(invitation)
    await session.commit()
    return True


async def get_invitation_stats(
    session: AsyncSession,
    created_by_id: Optional[int] = None,
    club_id: Optional[int] = None,
) -> dict:
    """Получить статистику по приглашениям"""
    conditions = []
    if created_by_id:
        conditions.append(Invitation.created_by_id == created_by_id)
    if club_id:
        conditions.append(Invitation.club_id == club_id)

    base_condition = and_(*conditions) if conditions else True

    # Общее количество
    total_result = await session.execute(
        select(func.count(Invitation.id)).where(base_condition)
    )
    total = total_result.scalar() or 0

    # Использованные
    used_result = await session.execute(
        select(func.count(Invitation.id)).where(
            and_(base_condition, Invitation.is_used == True)
        )
    )
    used = used_result.scalar() or 0

    # Активные (не использованные и не истекшие)
    pending_result = await session.execute(
        select(func.count(Invitation.id)).where(
            and_(
                base_condition,
                Invitation.is_used == False,
            )
        )
    )
    pending = pending_result.scalar() or 0

    # По ролям
    by_role_result = await session.execute(
        select(Invitation.role, func.count(Invitation.id))
        .where(base_condition)
        .group_by(Invitation.role)
    )
    by_role = {role.value: count for role, count in by_role_result}

    return {
        "total_invitations": total,
        "used_invitations": used,
        "pending_invitations": pending,
        "expired_invitations": total - used - pending,
        "by_role": by_role,
    }
