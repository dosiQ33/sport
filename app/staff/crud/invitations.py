from typing import Optional, List
from datetime import datetime, timezone, timedelta
from sqlalchemy import and_, func, or_
from sqlalchemy.future import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import db_operation, with_db_transaction
from app.core.exceptions import (
    NotFoundError,
    DuplicateError,
    ValidationError,
    PermissionDeniedError,
    BusinessLogicError,
)
from app.staff.models.invitations import Invitation, InvitationStatus
from app.staff.models.users import UserStaff
from app.staff.models.clubs import Club
from app.staff.models.roles import Role, RoleType
from app.staff.models.user_roles import UserRole
from app.staff.schemas.invitations import (
    InvitationCreateBySuperAdmin,
    InvitationCreateByOwner,
)


@db_operation
async def get_active_invitation_by_phone_role_club(
    session: AsyncSession,
    phone_number: str,
    role: RoleType,
    club_id: Optional[int] = None,
) -> Optional[Invitation]:
    """Получить активное приглашение для конкретной комбинации номер+роль+клуб"""
    if not phone_number or not phone_number.strip():
        raise ValidationError("Phone number cannot be empty")

    if not role:
        raise ValidationError("Role is required")

    conditions = [
        Invitation.phone_number == phone_number.strip(),
        Invitation.role == role,
        Invitation.status == InvitationStatus.PENDING,
        Invitation.expires_at > datetime.now(timezone.utc),
    ]

    if club_id is not None:
        if club_id <= 0:
            raise ValidationError("Club ID must be positive")
        conditions.append(Invitation.club_id == club_id)
    else:
        # Для owner приглашений club_id должен быть NULL
        conditions.append(Invitation.club_id.is_(None))

    result = await session.execute(
        select(Invitation)
        .options(
            selectinload(Invitation.club),
            selectinload(Invitation.created_by),
        )
        .where(and_(*conditions))
    )
    return result.scalar_one_or_none()


@db_operation
async def get_pending_invitations_by_phone(
    session: AsyncSession, phone_number: str
) -> List[Invitation]:
    """Получить все ожидающие приглашения для номера телефона"""
    if not phone_number or not phone_number.strip():
        raise ValidationError("Phone number cannot be empty")

    result = await session.execute(
        select(Invitation)
        .options(
            selectinload(Invitation.club),
            selectinload(Invitation.created_by),
        )
        .where(
            and_(
                Invitation.phone_number == phone_number.strip(),
                Invitation.status == InvitationStatus.PENDING,
                Invitation.expires_at > datetime.now(timezone.utc),
            )
        )
        .order_by(Invitation.created_at.desc())
    )
    return result.scalars().all()


@db_operation
async def get_pending_invitations_by_user_id(
    session: AsyncSession, user_id: int
) -> List[Invitation]:
    """Получить все ожидающие приглашения для пользователя по его ID"""
    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    # Сначала получаем номер телефона пользователя
    user_result = await session.execute(
        select(UserStaff.phone_number).where(UserStaff.id == user_id)
    )
    phone_number = user_result.scalar_one_or_none()

    if not phone_number:
        raise NotFoundError("User", str(user_id))

    return await get_pending_invitations_by_phone(session, phone_number)


@db_operation
async def get_invitation_by_id(
    session: AsyncSession, invitation_id: int
) -> Optional[Invitation]:
    """Получить приглашение по ID"""
    if not invitation_id or invitation_id <= 0:
        raise ValidationError("Invitation ID must be positive")

    result = await session.execute(
        select(Invitation)
        .options(
            selectinload(Invitation.club),
            selectinload(Invitation.created_by),
            selectinload(Invitation.responded_by),
        )
        .where(Invitation.id == invitation_id)
    )
    invitation = result.scalar_one_or_none()

    if not invitation:
        raise NotFoundError("Invitation", str(invitation_id))

    return invitation


async def create_invitation_by_superadmin(
    session: AsyncSession,
    invitation_data: InvitationCreateBySuperAdmin,
    created_by_type: str = "superadmin",
    expires_days: int = 7,
) -> Invitation:
    """Создать приглашение от суперадмина"""

    async def _create_invitation_operation(session: AsyncSession):
        # Проверяем, что не существует активного приглашения для этой комбинации
        existing = await session.execute(
            select(Invitation).where(
                and_(
                    Invitation.phone_number == invitation_data.phone_number.strip(),
                    Invitation.role == invitation_data.role,
                    Invitation.club_id == invitation_data.club_id,
                    Invitation.status == InvitationStatus.PENDING,
                    Invitation.expires_at > datetime.now(timezone.utc),
                )
            )
        )

        if existing.scalar_one_or_none():
            raise DuplicateError(
                "Active invitation",
                "phone_number+role+club",
                f"{invitation_data.phone_number} with role {invitation_data.role}",
            )

        # Для owner приглашений club_id должен быть NULL
        if invitation_data.role == RoleType.owner and invitation_data.club_id:
            raise ValidationError("Owner invitations should not have club_id")

        # Если указан club_id, проверяем существование клуба
        if invitation_data.club_id:
            club_result = await session.execute(
                select(Club).where(Club.id == invitation_data.club_id)
            )
            if not club_result.scalar_one_or_none():
                raise NotFoundError("Club", str(invitation_data.club_id))

        # Вычисляем время истечения
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

        db_invitation = Invitation(
            **invitation_data.model_dump(),
            created_by_id=None,  # SuperAdmin не в базе
            created_by_type=created_by_type,
            status=InvitationStatus.PENDING,
            expires_at=expires_at,
        )

        session.add(db_invitation)
        return db_invitation

    # Выполняем операцию в транзакции
    db_invitation = await with_db_transaction(session, _create_invitation_operation)

    # Загружаем связанные данные
    await session.refresh(db_invitation, ["club"])
    return db_invitation


async def create_invitation_by_owner(
    session: AsyncSession,
    invitation_data: InvitationCreateByOwner,
    owner_id: int,
    club_id: int,
    expires_days: int = 7,
) -> Invitation:
    """Создать приглашение от владельца клуба"""
    if not owner_id or owner_id <= 0:
        raise ValidationError("Owner ID must be positive")

    if not club_id or club_id <= 0:
        raise ValidationError("Club ID must be positive")

    async def _create_invitation_operation(session: AsyncSession):
        # Проверяем, что не существует активного приглашения для этой комбинации
        existing = await session.execute(
            select(Invitation).where(
                and_(
                    Invitation.phone_number == invitation_data.phone_number.strip(),
                    Invitation.role == invitation_data.role,
                    Invitation.club_id == club_id,
                    Invitation.status == InvitationStatus.PENDING,
                    Invitation.expires_at > datetime.now(timezone.utc),
                )
            )
        )

        if existing.scalar_one_or_none():
            raise DuplicateError(
                "Active invitation",
                "phone_number+role+club",
                f"{invitation_data.phone_number} in this club with role {invitation_data.role}",
            )

        # Проверяем, что клуб существует и принадлежит owner
        club_result = await session.execute(
            select(Club).where(and_(Club.id == club_id, Club.owner_id == owner_id))
        )
        club = club_result.scalar_one_or_none()
        if not club:
            raise NotFoundError("Club", f"Club {club_id} not found or you don't own it")

        # Проверяем, что owner не приглашает сам себя
        owner_result = await session.execute(
            select(UserStaff.phone_number).where(UserStaff.id == owner_id)
        )
        owner_phone = owner_result.scalar_one_or_none()
        if not owner_phone:
            raise NotFoundError("Owner", str(owner_id))

        if owner_phone == invitation_data.phone_number.strip():
            raise ValidationError("Cannot create invitation for yourself")

        # Проверяем, что приглашение не создается для уже существующего сотрудника клуба
        invited_user_result = await session.execute(
            select(UserStaff.id).where(
                UserStaff.phone_number == invitation_data.phone_number.strip()
            )
        )
        invited_user_id = invited_user_result.scalar_one_or_none()

        if invited_user_id:
            # Проверяем, не является ли приглашаемый уже активным сотрудником клуба
            existing_role_result = await session.execute(
                select(UserRole).where(
                    and_(
                        UserRole.user_id == invited_user_id,
                        UserRole.club_id == club_id,
                        UserRole.is_active == True,
                    )
                )
            )
            if existing_role_result.scalar_one_or_none():
                raise ValidationError("User is already a staff member of this club")
            # Note: Users with inactive roles (previously removed) CAN be re-invited

        # Не-owner роли ДОЛЖНЫ иметь club_id
        if invitation_data.role == RoleType.owner:
            raise ValidationError("Owners cannot invite other owners")

        # Вычисляем время истечения
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

        db_invitation = Invitation(
            phone_number=invitation_data.phone_number.strip(),
            role=invitation_data.role,
            club_id=club_id,
            created_by_id=owner_id,
            created_by_type="owner",
            status=InvitationStatus.PENDING,
            expires_at=expires_at,
        )

        session.add(db_invitation)
        return db_invitation

    # Выполняем операцию в транзакции
    db_invitation = await with_db_transaction(session, _create_invitation_operation)

    # Загружаем связанные данные
    await session.refresh(db_invitation, ["club", "created_by"])
    return db_invitation


async def accept_invitation(
    session: AsyncSession, invitation_id: int, user_id: int
) -> Invitation:
    """Принять приглашение пользователем"""
    if not invitation_id or invitation_id <= 0:
        raise ValidationError("Invitation ID must be positive")

    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    async def _accept_invitation_operation(session: AsyncSession):
        # Получаем приглашение
        invitation = await get_invitation_by_id(session, invitation_id)

        # Проверяем, что пользователь существует
        user_result = await session.execute(
            select(UserStaff).where(UserStaff.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise NotFoundError("User", str(user_id))

        # Проверяем, что номер телефона совпадает
        if invitation.phone_number != user.phone_number:
            raise PermissionDeniedError(
                "accept", "invitation", "Phone number does not match"
            )

        # Проверяем статус приглашения
        if invitation.status != InvitationStatus.PENDING:
            raise BusinessLogicError(
                f"Cannot accept invitation with status {invitation.status}"
            )

        # Проверяем, что приглашение не истекло
        if invitation.expires_at <= datetime.now(timezone.utc):
            raise BusinessLogicError("Invitation has expired")

        # Проверяем существующую роль пользователя в клубе
        if invitation.club_id:
            existing_role_result = await session.execute(
                select(UserRole).where(
                    and_(
                        UserRole.user_id == user_id,
                        UserRole.club_id == invitation.club_id,
                    )
                )
            )
            existing_role = existing_role_result.scalar_one_or_none()
            
            if existing_role:
                if existing_role.is_active:
                    raise BusinessLogicError("User already has an active role in this club")
                # User was previously removed - reactivate their role
                # Get the new role ID
                role_result = await session.execute(
                    select(Role).where(Role.code == invitation.role)
                )
                role = role_result.scalar_one_or_none()
                if not role:
                    raise NotFoundError("Role", invitation.role.value)
                
                # Reactivate the existing role with the new role type
                existing_role.is_active = True
                existing_role.role_id = role.id
                existing_role.joined_at = datetime.now(timezone.utc)
                existing_role.left_at = None

        # Обновляем статус приглашения
        invitation.status = InvitationStatus.ACCEPTED
        invitation.responded_by_id = user_id
        invitation.responded_at = datetime.now(timezone.utc)

        # Создаем запись в user_roles если есть club_id и не было существующей роли
        if invitation.club_id:
            # Check if we already handled an existing role above
            existing_role_check = await session.execute(
                select(UserRole).where(
                    and_(
                        UserRole.user_id == user_id,
                        UserRole.club_id == invitation.club_id,
                    )
                )
            )
            if not existing_role_check.scalar_one_or_none():
                # No existing role, create new one
                # Получаем роль
                role_result = await session.execute(
                    select(Role).where(Role.code == invitation.role)
                )
                role = role_result.scalar_one_or_none()
                if not role:
                    raise NotFoundError("Role", invitation.role.value)

                # Создаем запись о роли в клубе
                user_role = UserRole(
                    user_id=user_id,
                    club_id=invitation.club_id,
                    role_id=role.id,
                    is_active=True,
                )
                session.add(user_role)

        return invitation

    # Выполняем операцию в транзакции
    invitation = await with_db_transaction(session, _accept_invitation_operation)

    # Загружаем связанные данные
    await session.refresh(invitation, ["club", "created_by", "responded_by"])
    return invitation


async def decline_invitation(
    session: AsyncSession,
    invitation_id: int,
    user_id: int,
    reason: Optional[str] = None,
) -> Invitation:
    """Отклонить приглашение пользователем"""
    if not invitation_id or invitation_id <= 0:
        raise ValidationError("Invitation ID must be positive")

    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    async def _decline_invitation_operation(session: AsyncSession):
        # Получаем приглашение
        invitation = await get_invitation_by_id(session, invitation_id)

        # Проверяем, что пользователь существует
        user_result = await session.execute(
            select(UserStaff).where(UserStaff.id == user_id)
        )
        user = user_result.scalar_one_or_none()
        if not user:
            raise NotFoundError("User", str(user_id))

        # Проверяем, что номер телефона совпадает
        if invitation.phone_number != user.phone_number:
            raise PermissionDeniedError(
                "decline", "invitation", "Phone number does not match"
            )

        # Проверяем статус приглашения
        if invitation.status != InvitationStatus.PENDING:
            raise BusinessLogicError(
                f"Cannot decline invitation with status {invitation.status}"
            )

        # Обновляем статус приглашения
        invitation.status = InvitationStatus.DECLINED
        invitation.responded_by_id = user_id
        invitation.responded_at = datetime.now(timezone.utc)

        # Можно сохранить причину в дополнительном поле (пока не реализовано)
        # invitation.decline_reason = reason

        return invitation

    # Выполняем операцию в транзакции
    invitation = await with_db_transaction(session, _decline_invitation_operation)

    # Загружаем связанные данные
    await session.refresh(invitation, ["club", "created_by", "responded_by"])
    return invitation


@db_operation
async def mark_invitation_as_auto_accepted(
    session: AsyncSession, invitation_id: int, user_id: int
) -> bool:
    """Пометить приглашение как автоматически принятое (при регистрации)"""
    if not invitation_id or invitation_id <= 0:
        raise ValidationError("Invitation ID must be positive")

    if not user_id or user_id <= 0:
        raise ValidationError("User ID must be positive")

    invitation = await get_invitation_by_id(session, invitation_id)

    if invitation.status != InvitationStatus.PENDING:
        raise BusinessLogicError(
            f"Cannot auto-accept invitation with status {invitation.status}"
        )

    invitation.status = InvitationStatus.AUTO_ACCEPTED
    invitation.responded_by_id = user_id
    invitation.responded_at = datetime.now(timezone.utc)

    await session.commit()
    return True


@db_operation
async def delete_invitation(
    session: AsyncSession, invitation_id: int, deleter_id: int
) -> bool:
    """Удалить приглашение"""
    if not invitation_id or invitation_id <= 0:
        raise ValidationError("Invitation ID must be positive")

    if not deleter_id or deleter_id <= 0:
        raise ValidationError("Deleter ID must be positive")

    invitation = await get_invitation_by_id(session, invitation_id)

    # Проверяем права на удаление
    if invitation.created_by_id and invitation.created_by_id != deleter_id:
        # Проверяем, существует ли пользователь-создатель
        deleter_result = await session.execute(
            select(UserStaff).where(UserStaff.id == deleter_id)
        )
        if not deleter_result.scalar_one_or_none():
            raise NotFoundError("User", str(deleter_id))

        raise PermissionDeniedError(
            "delete", "invitation", "You can only delete invitations you created"
        )

    # Нельзя удалять обработанные приглашения
    if invitation.status != InvitationStatus.PENDING:
        raise ValidationError(
            f"Cannot delete invitation with status {invitation.status.value}"
        )

    await session.delete(invitation)
    await session.commit()
    return True


@db_operation
async def get_invitations_paginated(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 10,
    created_by_id: Optional[int] = None,
    club_id: Optional[int] = None,
    status: Optional[InvitationStatus] = None,
    role: Optional[RoleType] = None,
    include_expired: bool = False,
):
    """Получить список приглашений с пагинацией"""
    if skip < 0:
        raise ValidationError("Skip parameter must be >= 0")

    if limit <= 0 or limit > 100:
        raise ValidationError("Limit must be between 1 and 100")

    base_query = select(Invitation).options(
        selectinload(Invitation.club),
        selectinload(Invitation.created_by),
        selectinload(Invitation.responded_by),
    )
    count_query = select(func.count(Invitation.id))

    conditions = []

    if created_by_id is not None:
        if created_by_id <= 0:
            raise ValidationError("Created by ID must be positive")
        conditions.append(Invitation.created_by_id == created_by_id)

    if club_id is not None:
        if club_id <= 0:
            raise ValidationError("Club ID must be positive")
        conditions.append(Invitation.club_id == club_id)

    if status is not None:
        conditions.append(Invitation.status == status)

    if role is not None:
        conditions.append(Invitation.role == role)

    # По умолчанию не показываем истекшие pending приглашения
    if not include_expired:
        conditions.append(
            or_(
                Invitation.status != InvitationStatus.PENDING,
                Invitation.expires_at > datetime.now(timezone.utc),
            )
        )

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


@db_operation
async def get_invitation_stats(
    session: AsyncSession,
    created_by_id: Optional[int] = None,
    club_id: Optional[int] = None,
) -> dict:
    """Получить статистику по приглашениям"""
    conditions = []

    if created_by_id:
        if created_by_id <= 0:
            raise ValidationError("Created by ID must be positive")
        conditions.append(Invitation.created_by_id == created_by_id)

    if club_id:
        if club_id <= 0:
            raise ValidationError("Club ID must be positive")
        conditions.append(Invitation.club_id == club_id)

    base_condition = and_(*conditions) if conditions else True

    # Общее количество
    total_result = await session.execute(
        select(func.count(Invitation.id)).where(base_condition)
    )
    total = total_result.scalar() or 0

    # По статусам
    by_status_result = await session.execute(
        select(Invitation.status, func.count(Invitation.id))
        .where(base_condition)
        .group_by(Invitation.status)
    )
    by_status = {status.value: count for status, count in by_status_result}

    # По ролям
    by_role_result = await session.execute(
        select(Invitation.role, func.count(Invitation.id))
        .where(base_condition)
        .group_by(Invitation.role)
    )
    by_role = {role.value: count for role, count in by_role_result}

    return {
        "total_invitations": total,
        "by_status": by_status,
        "by_role": by_role,
    }


@db_operation
async def cleanup_expired_invitations(session: AsyncSession) -> int:
    """Обновить статус истекших pending приглашений"""
    now = datetime.now(timezone.utc)

    # Находим все pending приглашения, которые истекли
    result = await session.execute(
        select(Invitation).where(
            and_(
                Invitation.status == InvitationStatus.PENDING,
                Invitation.expires_at <= now,
            )
        )
    )
    expired_invitations = result.scalars().all()

    count = len(expired_invitations)
    for invitation in expired_invitations:
        invitation.status = InvitationStatus.EXPIRED

    await session.commit()
    return count
