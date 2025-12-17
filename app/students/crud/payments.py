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
    Complete a payment and create student enrollment.
    This is a mock function that simulates successful payment completion.
    In production, this would be called by a payment gateway webhook.
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
    
    # Find a group to enroll the student in
    # First, try to find a group in the club associated with the tariff
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
    
    if group:
        # Check if student is already enrolled in this group
        existing_enrollment_query = select(StudentEnrollment).where(
            and_(
                StudentEnrollment.student_id == student_id,
                StudentEnrollment.group_id == group.id,
                StudentEnrollment.status.in_([EnrollmentStatus.active, EnrollmentStatus.new])
            )
        )
        existing_result = await session.execute(existing_enrollment_query)
        existing_enrollment = existing_result.scalar_one_or_none()
        
        if existing_enrollment:
            # Extend the existing enrollment
            if tariff.validity_days:
                existing_enrollment.end_date = existing_enrollment.end_date + timedelta(days=tariff.validity_days)
            else:
                existing_enrollment.end_date = existing_enrollment.end_date + timedelta(days=30)
            enrollment_id = existing_enrollment.id
        else:
            # Create new enrollment
            start_date = date.today()
            end_date = start_date + timedelta(days=tariff.validity_days or 30)
            
            enrollment = StudentEnrollment(
                student_id=student_id,
                group_id=group.id,
                status=EnrollmentStatus.new,
                start_date=start_date,
                end_date=end_date,
                tariff_id=tariff.id,
                tariff_name=tariff.name,
                price=tariff.price,
                freeze_days_total=7,  # Default freeze days
                freeze_days_used=0,
                is_active=True,
            )
            session.add(enrollment)
            await session.flush()
            enrollment_id = enrollment.id
    
    # Update payment status
    payment.status = PaymentStatus.paid
    payment.payment_date = datetime.now()
    payment.enrollment_id = enrollment_id
    
    await session.commit()
    
    return CompletePaymentResponse(
        success=True,
        payment_id=payment_id,
        enrollment_id=enrollment_id,
        message="Payment completed successfully. Membership activated."
    )
