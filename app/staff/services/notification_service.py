"""
Notification Service - Centralized notification logic for staff members.

This service handles sending notifications (Telegram + in-app) to relevant staff members
based on their roles and relationships to clubs/groups.
"""
import asyncio
import logging
from typing import Set, Optional
from datetime import date
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.telegram_sender import send_telegram_message, BotType
from app.staff.models.users import UserStaff
from app.staff.models.user_roles import UserRole
from app.staff.models.roles import Role, RoleType
from app.staff.models.groups import Group
from app.staff.models.sections import Section
from app.staff.models.clubs import Club
from app.staff.models.enrollments import StudentEnrollment
from app.students.models.users import UserStudent
from app.staff.crud.notifications import create_notification
from app.staff.schemas.notifications import NotificationCreate

logger = logging.getLogger(__name__)


async def get_notification_recipients(
    session: AsyncSession,
    club_id: int,
    group_id: Optional[int] = None,
    include_coach: bool = True
) -> Set[int]:
    """
    Get set of staff user IDs who should receive notifications.
    
    Args:
        session: Database session
        club_id: Club ID
        group_id: Optional group ID (if provided, includes the coach)
        include_coach: Whether to include the group coach (default: True)
        
    Returns:
        Set of user IDs to notify
    """
    recipients = set()
    
    # Get owners and admins of the club
    owner_admin_query = (
        select(UserRole.user_id)
        .join(Role, UserRole.role_id == Role.id)
        .where(
            and_(
                UserRole.club_id == club_id,
                UserRole.is_active == True,
                Role.code.in_([RoleType.owner, RoleType.admin])
            )
        )
    )
    owner_admin_result = await session.execute(owner_admin_query)
    owner_admin_ids = owner_admin_result.scalars().all()
    recipients.update(owner_admin_ids)
    
    # Add coach if group_id is provided
    if include_coach and group_id:
        group_query = select(Group.coach_id).where(Group.id == group_id)
        group_result = await session.execute(group_query)
        coach_id = group_result.scalar_one_or_none()
        if coach_id:
            recipients.add(coach_id)
            logger.debug(f"Added coach {coach_id} to notification recipients for group {group_id}")
    
    return recipients


async def send_membership_notification(
    session: AsyncSession,
    notification_type: str,
    student_id: int,
    enrollment: StudentEnrollment,
    additional_data: Optional[dict] = None
) -> None:
    """
    Send notification about membership changes to relevant staff members.
    
    Args:
        session: Database session
        notification_type: Type of notification ('freeze', 'unfreeze', 'extend', 'buy', 'upgrade')
        student_id: Student user ID
        enrollment: StudentEnrollment object (must have group.section.club loaded)
        additional_data: Optional dict with additional data (days, amount, etc.)
    """
    try:
        logger.debug(f"Starting notification for type: {notification_type}, enrollment: {enrollment.id}, student: {student_id}")
        
        # Ensure relationships are loaded
        if not enrollment.group:
            logger.error(f"Enrollment {enrollment.id} missing group relationship")
            return
        if not enrollment.group.section:
            logger.error(f"Enrollment {enrollment.id} missing section relationship")
            return
        if not enrollment.group.section.club:
            logger.error(f"Enrollment {enrollment.id} missing club relationship")
            return
        
        club_id = enrollment.group.section.club_id
        group_id = enrollment.group_id
        club_name = enrollment.group.section.club.name
        group_name = enrollment.group.name
        
        # Get student info
        student_query = select(UserStudent).where(UserStudent.id == student_id)
        student_result = await session.execute(student_query)
        student = student_result.scalar_one_or_none()
        
        if not student:
            logger.warning(f"Student {student_id} not found, skipping notification")
            return
        
        student_name = f"{student.first_name} {student.last_name or ''}".strip()
        
        # Build notification messages based on type
        notification_config = _get_notification_config(
            notification_type,
            student_name,
            club_name,
            group_name,
            additional_data or {}
        )
        
        if not notification_config:
            logger.warning(f"Unknown notification type: {notification_type}")
            return
        
        # Get recipients
        recipients = await get_notification_recipients(
            session,
            club_id=club_id,
            group_id=group_id,
            include_coach=True
        )
        
        if not recipients:
            logger.warning(f"No recipients found for club {club_id}, group {group_id}. Check if club has owners/admins or group has a coach.")
            return
        
        logger.info(f"Sending {notification_type} notification to {len(recipients)} recipients: {recipients}")
        
        # Send notifications to all recipients
        for recipient_id in recipients:
            try:
                staff_user = await session.get(UserStaff, recipient_id)
                if not staff_user:
                    continue
                
                # Send Telegram message
                if staff_user.telegram_id:
                    asyncio.create_task(send_telegram_message(
                        chat_id=staff_user.telegram_id,
                        text=notification_config['telegram_message'],
                        bot_type=BotType.STAFF
                    ))
                
                # Create in-app notification
                notification_data = NotificationCreate(
                    recipient_id=recipient_id,
                    title=notification_config['title'],
                    message=notification_config['in_app_message'],
                    metadata_json={
                        "type": notification_config['metadata_type'],
                        "student_id": student_id,
                        "group_id": group_id,
                        "club_id": club_id,
                        **notification_config.get('metadata_extra', {})
                    }
                )
                await create_notification(session, notification_data)
                logger.debug(f"Successfully created in-app notification for staff user {recipient_id}")
                
            except Exception as e:
                logger.error(f"Failed to notify staff user {recipient_id}: {e}", exc_info=True)
                
    except Exception as e:
        logger.error(f"Failed to send membership notification: {e}", exc_info=True)


def _get_notification_config(
    notification_type: str,
    student_name: str,
    club_name: str,
    group_name: str,
    additional_data: dict
) -> Optional[dict]:
    """Get notification configuration based on type."""
    
    configs = {
        'freeze': {
            'title': '❄️ Абонемент заморожен',
            'telegram_message': (
                f"❄️ <b>Уведомление о заморозке</b>\n\n"
                f"Студент: <b>{student_name}</b>\n"
                f"Клуб: {club_name}\n"
                f"Группа: {group_name}\n"
                f"Период: {additional_data.get('start_date', '').strftime('%d.%m.%Y')} - {additional_data.get('end_date', '').strftime('%d.%m.%Y')}\n"
                f"Дней: {additional_data.get('days', 0)}"
            ),
            'in_app_message': (
                f"Студент {student_name} заморозил абонемент в группе {group_name} ({club_name}) "
                f"на {additional_data.get('days', 0)} дней."
            ),
            'metadata_type': 'membership_freeze',
            'metadata_extra': {'days': additional_data.get('days', 0)}
        },
        'unfreeze': {
            'title': '✅ Абонемент разморожен',
            'telegram_message': (
                f"✅ <b>Уведомление о разморозке</b>\n\n"
                f"Студент: <b>{student_name}</b>\n"
                f"Клуб: {club_name}\n"
                f"Группа: {group_name}\n"
                f"Абонемент активирован"
            ),
            'in_app_message': (
                f"Студент {student_name} разморозил абонемент в группе {group_name} ({club_name})."
            ),
            'metadata_type': 'membership_unfreeze',
            'metadata_extra': {}
        },
        'extend': {
            'title': '📅 Абонемент продлен',
            'telegram_message': (
                f"📅 <b>Уведомление о продлении</b>\n\n"
                f"Студент: <b>{student_name}</b>\n"
                f"Клуб: {club_name}\n"
                f"Группа: {group_name}\n"
                f"Продлено на: {additional_data.get('days', 0)} дней\n"
                f"Новая дата окончания: {additional_data.get('new_end_date', '').strftime('%d.%m.%Y')}"
            ),
            'in_app_message': (
                f"Абонемент студента {student_name} в группе {group_name} ({club_name}) "
                f"продлен на {additional_data.get('days', 0)} дней."
            ),
            'metadata_type': 'membership_extend',
            'metadata_extra': {'days': additional_data.get('days', 0)}
        },
        'buy': {
            'title': '🛒 Новый абонемент приобретен',
            'telegram_message': (
                f"🛒 <b>Новый абонемент</b>\n\n"
                f"Студент: <b>{student_name}</b>\n"
                f"Клуб: {club_name}\n"
                f"Группа: {group_name}\n"
                f"Тариф: {additional_data.get('tariff_name', 'N/A')}\n"
                f"Период: {additional_data.get('start_date', '').strftime('%d.%m.%Y')} - {additional_data.get('end_date', '').strftime('%d.%m.%Y')}\n"
                f"Сумма: {additional_data.get('price', 0):.0f} ₸"
            ),
            'in_app_message': (
                f"Студент {student_name} приобрел новый абонемент в группе {group_name} ({club_name}). "
                f"Тариф: {additional_data.get('tariff_name', 'N/A')}."
            ),
            'metadata_type': 'membership_buy',
            'metadata_extra': {
                'tariff_id': additional_data.get('tariff_id'),
                'tariff_name': additional_data.get('tariff_name'),
                'price': additional_data.get('price', 0)
            }
        },
        'upgrade': {
            'title': '⬆️ Абонемент обновлен',
            'telegram_message': (
                f"⬆️ <b>Обновление абонемента</b>\n\n"
                f"Студент: <b>{student_name}</b>\n"
                f"Клуб: {club_name}\n"
                f"Группа: {group_name}\n"
                f"Новый тариф: {additional_data.get('tariff_name', 'N/A')}\n"
                f"Период: {additional_data.get('start_date', '').strftime('%d.%m.%Y')} - {additional_data.get('end_date', '').strftime('%d.%m.%Y')}"
            ),
            'in_app_message': (
                f"Студент {student_name} обновил абонемент в группе {group_name} ({club_name}). "
                f"Новый тариф: {additional_data.get('tariff_name', 'N/A')}."
            ),
            'metadata_type': 'membership_upgrade',
            'metadata_extra': {
                'tariff_id': additional_data.get('tariff_id'),
                'tariff_name': additional_data.get('tariff_name')
            }
        }
    }
    
    return configs.get(notification_type)

