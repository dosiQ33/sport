"""Student CRUD Package"""
from .users import (
    get_user_student_by_telegram_id,
    get_user_student_by_id,
    get_user_students_paginated,
    create_user_student,
    update_user_student,
    update_user_student_preferences,
    get_user_student_preference,
)

from .memberships import (
    get_student_memberships,
    get_active_memberships,
    has_active_membership,
    get_membership_history,
    freeze_student_membership,
    unfreeze_student_membership,
    get_membership_stats,
)

from .attendance import (
    check_in_student,
    get_student_attendance,
    get_attendance_stats,
)

from .payments import (
    get_student_payments,
    initiate_payment,
    get_payment_stats,
)

from .schedule import (
    get_student_upcoming_sessions,
    get_all_available_sessions,
    get_trainers_for_student,
)

from .clubs import (
    get_clubs_list,
    get_club_details,
    get_student_club_ids,
    get_nearest_club,
)

__all__ = [
    # Users
    "get_user_student_by_telegram_id",
    "get_user_student_by_id",
    "get_user_students_paginated",
    "create_user_student",
    "update_user_student",
    "update_user_student_preferences",
    "get_user_student_preference",
    # Memberships
    "get_student_memberships",
    "get_active_memberships",
    "has_active_membership",
    "get_membership_history",
    "freeze_student_membership",
    "unfreeze_student_membership",
    "get_membership_stats",
    # Attendance
    "check_in_student",
    "get_student_attendance",
    "get_attendance_stats",
    # Payments
    "get_student_payments",
    "initiate_payment",
    "get_payment_stats",
    # Schedule
    "get_student_upcoming_sessions",
    "get_all_available_sessions",
    "get_trainers_for_student",
    # Clubs
    "get_clubs_list",
    "get_club_details",
    "get_student_club_ids",
    "get_nearest_club",
]
