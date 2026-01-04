"""Student Payments CRUD - Operations for payment tracking"""
import math
from typing import List, Tuple, Optional
from datetime import date, datetime
from sqlalchemy import and_, func, extract
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload, joinedload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import db_operation
from app.core.exceptions import NotFoundError, ValidationError
from app.students.models.payments import StudentPayment, PaymentStatus, PaymentMethod
from app.staff.models.clubs import Club
from app.staff.models.tariffs import Tariff
from app.staff.models.sections import Section
from app.staff.models.groups import Group
from app.staff.models.enrollments import StudentEnrollment, EnrollmentStatus
from app.students.schemas.payments import (
    PaymentRecordRead,
    PaymentStatusEnum,
    PaymentMethodEnum,
    InitiatePaymentRequest,
    InitiatePaymentResponse,
    PaymentStatsResponse,
    CompletePaymentResponse,
)


def calculate_validity_days(tariff: Tariff) -> int:
    """
    Calculate validity days based on tariff payment_type.
    
    Rules:
    - monthly: 30 days (or use validity_days if explicitly set)
    - semi_annual: 180 days (6 months)
    - annual: 365 days (1 year)
    - session_pack: use validity_days from tariff (required)
    
    Args:
        tariff: Tariff object with payment_type and validity_days
        
    Returns:
        Number of validity days
    """
    if tariff.payment_type == "annual":
        return 365
    elif tariff.payment_type == "semi_annual":
        return 180
    elif tariff.payment_type == "session_pack":
        # For session_pack, validity_days is required
        if not tariff.validity_days:
            raise ValidationError("validity_days is required for session_pack tariffs")
        return tariff.validity_days
    else:  # monthly or default
        # Use validity_days if set, otherwise default to 30 days
        return tariff.validity_days if tariff.validity_days else 30


@db_operation
async def get_student_payments(
    session: AsyncSession,
    student_id: int,
    skip: int = 0,
    limit: int = 20,
    status: Optional[str] = None
) -> Tuple[List[PaymentRecordRead], int]:
    """Get student payment records"""
    base_query = (
        select(StudentPayment, Club, Tariff)
        .select_from(StudentPayment)
        .outerjoin(Club, StudentPayment.club_id == Club.id)
        .outerjoin(Tariff, StudentPayment.tariff_id == Tariff.id)
        .where(StudentPayment.student_id == student_id)
    )
    
    if status:
        base_query = base_query.where(StudentPayment.status == status)
    
    # Count
    count_query = select(func.count()).select_from(base_query.subquery())
    total_result = await session.execute(count_query)
    total = total_result.scalar() or 0
    
    # Get paginated results
    query = base_query.order_by(StudentPayment.created_at.desc()).offset(skip).limit(limit)
    result = await session.execute(query)
    rows = result.fetchall()
    
    payments = []
    for row in rows:
        payment, club, tariff = row
        
        payments.append(PaymentRecordRead(
            id=payment.id,
            club_id=payment.club_id,
            club_name=club.name if club else None,
            amount=float(payment.amount),
            currency=payment.currency,
            status=PaymentStatusEnum(payment.status.value) if isinstance(payment.status, PaymentStatus) else PaymentStatusEnum(payment.status),
            payment_method=PaymentMethodEnum(payment.payment_method.value) if payment.payment_method and isinstance(payment.payment_method, PaymentMethod) else (PaymentMethodEnum(payment.payment_method) if payment.payment_method else None),
            description=payment.description,
            tariff_name=tariff.name if tariff else None,
            payment_date=payment.payment_date,
            created_at=payment.created_at,
        ))
    
    return payments, total


@db_operation
async def initiate_payment(
    session: AsyncSession,
    student_id: int,
    request: InitiatePaymentRequest
) -> InitiatePaymentResponse:
    """Initiate a new payment"""
    # Get tariff
    tariff_query = select(Tariff).where(Tariff.id == request.tariff_id)
    tariff_result = await session.execute(tariff_query)
    tariff = tariff_result.scalar_one_or_none()
    
    if not tariff:
        raise NotFoundError("Tariff", str(request.tariff_id))
    
    if not tariff.active:
        raise ValidationError("Tariff is not available")
    
    # Get club
    club_query = select(Club).where(Club.id == request.club_id)
    club_result = await session.execute(club_query)
    club = club_result.scalar_one_or_none()
    
    if not club:
        raise NotFoundError("Club", str(request.club_id))
    
    # Create payment record
    payment = StudentPayment(
        student_id=student_id,
        club_id=request.club_id,
        tariff_id=request.tariff_id,
        amount=tariff.price,
        currency="KZT",
        status=PaymentStatus.pending,
        payment_method=PaymentMethod(request.payment_method.value) if request.payment_method else None,
        description=f"Payment for {tariff.name} at {club.name}",
    )
    
    session.add(payment)
    await session.commit()
    await session.refresh(payment)
    
    # In a real implementation, this would integrate with a payment gateway
    # and return a redirect URL for payment processing
    return InitiatePaymentResponse(
        payment_id=payment.id,
        amount=float(payment.amount),
        currency=payment.currency,
        status=PaymentStatusEnum.pending,
        redirect_url=None,  # Would be set by payment gateway
        external_id=None,
    )


@db_operation
async def get_payment_stats(
    session: AsyncSession,
    student_id: int
) -> PaymentStatsResponse:
    """Get payment statistics for a student"""
    today = date.today()
    month_start = today.replace(day=1)
    
    # Total paid
    total_query = (
        select(func.sum(StudentPayment.amount))
        .where(
            and_(
                StudentPayment.student_id == student_id,
                StudentPayment.status == PaymentStatus.paid
            )
        )
    )
    total_result = await session.execute(total_query)
    total_paid = float(total_result.scalar() or 0)
    
    # Pending payments
    pending_query = (
        select(func.count(StudentPayment.id))
        .where(
            and_(
                StudentPayment.student_id == student_id,
                StudentPayment.status == PaymentStatus.pending
            )
        )
    )
    pending_result = await session.execute(pending_query)
    pending_payments = pending_result.scalar() or 0
    
    # Payments this month
    month_count_query = (
        select(func.count(StudentPayment.id))
        .where(
            and_(
                StudentPayment.student_id == student_id,
                StudentPayment.status == PaymentStatus.paid,
                StudentPayment.payment_date >= month_start
            )
        )
    )
    month_count_result = await session.execute(month_count_query)
    payments_this_month = month_count_result.scalar() or 0
    
    # Amount this month
    month_amount_query = (
        select(func.sum(StudentPayment.amount))
        .where(
            and_(
                StudentPayment.student_id == student_id,
                StudentPayment.status == PaymentStatus.paid,
                StudentPayment.payment_date >= month_start
            )
        )
    )
    month_amount_result = await session.execute(month_amount_query)
    amount_this_month = float(month_amount_result.scalar() or 0)
    
    return PaymentStatsResponse(
        total_paid=total_paid,
        pending_payments=pending_payments,
        payments_this_month=payments_this_month,
        amount_this_month=amount_this_month,
    )


@db_operation
async def complete_payment(
    session: AsyncSession,
    student_id: int,
    payment_id: int
) -> CompletePaymentResponse:
    """
    Complete a payment and create/extend student enrollment.
    
    Logic:
    1. If buying same tariff with same group → extend current membership
    2. If buying different tariff:
       - If no active membership in club → start today
       - If active membership exists → schedule to start after current ends
    """
    from datetime import timedelta
    
    # Get the payment
    payment_query = select(StudentPayment).where(
        and_(
            StudentPayment.id == payment_id,
            StudentPayment.student_id == student_id
        )
    )
    payment_result = await session.execute(payment_query)
    payment = payment_result.scalar_one_or_none()
    
    if not payment:
        raise NotFoundError("Payment", str(payment_id))
    
    if payment.status == PaymentStatus.paid:
        return CompletePaymentResponse(
            success=True,
            payment_id=payment_id,
            enrollment_id=payment.enrollment_id,
            message="Payment already completed"
        )
    
    if payment.status != PaymentStatus.pending:
        raise ValidationError(f"Cannot complete payment with status: {payment.status}")
    
    # Get the tariff to determine enrollment duration
    tariff_query = select(Tariff).where(Tariff.id == payment.tariff_id)
    tariff_result = await session.execute(tariff_query)
    tariff = tariff_result.scalar_one_or_none()
    
    if not tariff:
        raise NotFoundError("Tariff", str(payment.tariff_id))
    
    # Check if tariff is deleted - cannot complete payment for deleted tariff
    if tariff.deleted_at is not None:
        raise ValidationError(
            "This tariff is no longer available. Please choose a different tariff."
        )
    
    # Find a group to enroll the student in
    group = None
    
    # If tariff has specific group_ids, use the first one
    if tariff.group_ids and len(tariff.group_ids) > 0:
        group_query = select(Group).where(Group.id == tariff.group_ids[0])
        group_result = await session.execute(group_query)
        group = group_result.scalar_one_or_none()
    
    # If no specific group, find any active group in the club
    if not group and payment.club_id:
        group_query = (
            select(Group)
            .join(Section, Group.section_id == Section.id)
            .where(
                and_(
                    Section.club_id == payment.club_id,
                    Group.active == True,
                    Section.active == True
                )
            )
            .limit(1)
        )
        group_result = await session.execute(group_query)
        group = group_result.scalar_one_or_none()
    
    enrollment_id = None
    message = "Payment completed successfully."
    notification_type = None
    enrollment = None
    
    if group:
        # Calculate validity days based on payment_type
        validity_days = calculate_validity_days(tariff)
        freeze_days = tariff.freeze_days_total or 0
        
        # Check if student has an existing active enrollment with SAME tariff in SAME group
        same_tariff_enrollment_query = select(StudentEnrollment).where(
            and_(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.group_id == group.id,
                StudentEnrollment.tariff_id == tariff.id,
                StudentEnrollment.status.in_([
                    EnrollmentStatus.active, 
                    EnrollmentStatus.new,
                    EnrollmentStatus.frozen
                ])
            )
        )
        same_tariff_result = await session.execute(same_tariff_enrollment_query)
        same_tariff_enrollment = same_tariff_result.scalar_one_or_none()
        
        if same_tariff_enrollment:
            # CASE 1: Same tariff, same group → EXTEND the existing membership
            same_tariff_enrollment.end_date = same_tariff_enrollment.end_date + timedelta(days=validity_days)
            # Add freeze days to available
            same_tariff_enrollment.freeze_days_total = (same_tariff_enrollment.freeze_days_total or 0) + freeze_days
            enrollment_id = same_tariff_enrollment.id
            enrollment = same_tariff_enrollment
            notification_type = 'extend'
            message = f"Membership extended by {validity_days} days."
        else:
            # Check if student has ANY active membership in this CLUB
            club_enrollment_query = (
                select(StudentEnrollment, Group, Section)
                .join(Group, StudentEnrollment.group_id == Group.id)
                .join(Section, Group.section_id == Section.id)
                .where(
                    and_(
                        StudentEnrollment.student_id == student_id,
                        Section.club_id == payment.club_id,
                        StudentEnrollment.status.in_([
                            EnrollmentStatus.active, 
                            EnrollmentStatus.new,
                            EnrollmentStatus.frozen
                        ])
                    )
                )
                .order_by(StudentEnrollment.end_date.desc())
            )
            club_enrollment_result = await session.execute(club_enrollment_query)
            active_club_enrollments = club_enrollment_result.fetchall()
            
            # Check if new tariff overlaps with any active membership
            # Only schedule if there's overlap (same groups/sections) or if it's an upgrade
            has_overlap = False
            overlapping_enrollment = None
            
            if active_club_enrollments:
                # Get the new tariff's coverage
                new_tariff_group_ids = set(tariff.group_ids or [])
                new_tariff_section_ids = set(tariff.section_ids or [])
                new_tariff_type = tariff.type
                
                # Check each active enrollment for overlap
                for enrollment_row in active_club_enrollments:
                    active_enrollment, active_group, active_section = enrollment_row
                    
                    # Check if new tariff overlaps with this active membership
                    overlap = False
                    
                    # Case 1: New tariff is full_club - overlaps with everything in club
                    if new_tariff_type == 'full_club':
                        overlap = True
                    
                    # Case 2: New tariff includes the active group
                    elif active_group.id in new_tariff_group_ids:
                        overlap = True
                    
                    # Case 3: New tariff includes the active section
                    elif active_section.id in new_tariff_section_ids:
                        overlap = True
                    
                    # Case 4: New tariff is full_section and includes active section
                    elif new_tariff_type == 'full_section' and active_section.id in new_tariff_section_ids:
                        overlap = True
                    
                    # Case 5: Active membership's group is in new tariff's groups
                    elif new_tariff_group_ids and active_group.id in new_tariff_group_ids:
                        overlap = True
                    
                    if overlap:
                        has_overlap = True
                        overlapping_enrollment = active_enrollment
                        break
            
            if has_overlap and overlapping_enrollment:
                # Check if there's already a scheduled membership in this club
                # Limit: only 1 scheduled membership per club allowed
                scheduled_check_query = (
                    select(StudentEnrollment)
                    .join(Group, StudentEnrollment.group_id == Group.id)
                    .join(Section, Group.section_id == Section.id)
                    .where(
                        and_(
                            StudentEnrollment.student_id == student_id,
                            Section.club_id == payment.club_id,
                            StudentEnrollment.status == EnrollmentStatus.scheduled
                        )
                    )
                )
                scheduled_result = await session.execute(scheduled_check_query)
                existing_scheduled = scheduled_result.scalar_one_or_none()
                
                if existing_scheduled:
                    raise ValidationError(
                        "You already have a scheduled membership for this club. "
                        "Only one scheduled membership is allowed per club."
                    )
                
                # CASE 2: Different tariff but overlaps with active membership → SCHEDULE after current ends
                # New membership starts the day after current one ends
                start_date = overlapping_enrollment.end_date + timedelta(days=1)
                end_date = start_date + timedelta(days=validity_days)
                
                enrollment = StudentEnrollment(
                    student_id=student_id,
                    group_id=group.id,
                    status=EnrollmentStatus.scheduled,  # Scheduled to start later
                    start_date=start_date,
                    end_date=end_date,
                    tariff_id=tariff.id,
                    tariff_name=tariff.name,
                    price=tariff.price,
                    freeze_days_total=freeze_days,
                    freeze_days_used=0,
                    is_active=True,
                )
                session.add(enrollment)
                await session.flush()
                enrollment_id = enrollment.id
                notification_type = 'upgrade'
                message = f"Membership scheduled to start on {start_date.strftime('%d.%m.%Y')} after current membership ends."
            else:
                # CASE 3: No active membership in club → START immediately
                start_date = date.today()
                end_date = start_date + timedelta(days=validity_days)
                
                enrollment = StudentEnrollment(
                    student_id=student_id,
                    group_id=group.id,
                    status=EnrollmentStatus.new,
                    start_date=start_date,
                    end_date=end_date,
                    tariff_id=tariff.id,
                    tariff_name=tariff.name,
                    price=tariff.price,
                    freeze_days_total=freeze_days,
                    freeze_days_used=0,
                    is_active=True,
                )
                session.add(enrollment)
                await session.flush()
                enrollment_id = enrollment.id
                notification_type = 'buy'
                message = "Membership activated."
    
    # Update payment status
    payment.status = PaymentStatus.paid
    payment.payment_date = datetime.now()
    payment.enrollment_id = enrollment_id
    
    await session.commit()
    
    # Refresh enrollment with relationships for notification
    if enrollment_id:
        enrollment_query = (
            select(StudentEnrollment)
            .options(
                joinedload(StudentEnrollment.group)
                .joinedload(Group.section)
                .joinedload(Section.club)
            )
            .where(StudentEnrollment.id == enrollment_id)
        )
        enrollment_result = await session.execute(enrollment_query)
        enrollment = enrollment_result.scalar_one_or_none()
    
    # NOTIFICATION: Notify staff about payment completion
    if enrollment and notification_type:
        try:
            from app.staff.services.notification_service import send_membership_notification
            
            additional_data = {
                'tariff_id': tariff.id,
                'tariff_name': tariff.name,
                'price': tariff.price,
                'start_date': enrollment.start_date,
                'end_date': enrollment.end_date
            }
            
            if notification_type == 'extend':
                additional_data['days'] = validity_days
                additional_data['new_end_date'] = enrollment.end_date
            
            await send_membership_notification(
                session=session,
                notification_type=notification_type,
                student_id=student_id,
                enrollment=enrollment,
                additional_data=additional_data
            )
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to send payment notification: {e}", exc_info=True)
    
    return CompletePaymentResponse(
        success=True,
        payment_id=payment_id,
        enrollment_id=enrollment_id,
        message=message
    )
