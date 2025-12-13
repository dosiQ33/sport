"""Student Schemas Package"""
from .users import (
    UserStudentBase,
    UserStudentCreate,
    UserStudentUpdate,
    UserStudentRead,
    UserStudentFilters,
    UserStudentListResponse,
    PreferencesUpdate,
)

from .memberships import (
    MembershipStatus,
    MembershipRead,
    MembershipHistoryRead,
    MembershipListResponse,
    MembershipHistoryResponse,
    FreezeMembershipRequest,
    UnfreezeMembershipRequest,
    MembershipStatsResponse,
)

from .attendance import (
    AttendanceStatus,
    CheckInRequest,
    CheckInResponse,
    AttendanceRecordRead,
    AttendanceListResponse,
    AttendanceStatsResponse,
)

from .payments import (
    PaymentStatusEnum,
    PaymentMethodEnum,
    PaymentRecordRead,
    PaymentListResponse,
    InitiatePaymentRequest,
    InitiatePaymentResponse,
    PaymentStatsResponse,
)

from .schedule import (
    SessionStatus,
    SessionRead,
    SessionListResponse,
    BookSessionRequest,
    BookSessionResponse,
    CancelBookingRequest,
    CancelBookingResponse,
    TrainerInfo,
    ScheduleFilters,
)

from .clubs import (
    ClubSectionRead,
    ClubTariffRead,
    ClubRead,
    ClubDetailRead,
    ClubListResponse,
    ClubLocationRead,
    NearestClubResponse,
)

__all__ = [
    # Users
    "UserStudentBase",
    "UserStudentCreate",
    "UserStudentUpdate",
    "UserStudentRead",
    "UserStudentFilters",
    "UserStudentListResponse",
    "PreferencesUpdate",
    # Memberships
    "MembershipStatus",
    "MembershipRead",
    "MembershipHistoryRead",
    "MembershipListResponse",
    "MembershipHistoryResponse",
    "FreezeMembershipRequest",
    "UnfreezeMembershipRequest",
    "MembershipStatsResponse",
    # Attendance
    "AttendanceStatus",
    "CheckInRequest",
    "CheckInResponse",
    "AttendanceRecordRead",
    "AttendanceListResponse",
    "AttendanceStatsResponse",
    # Payments
    "PaymentStatusEnum",
    "PaymentMethodEnum",
    "PaymentRecordRead",
    "PaymentListResponse",
    "InitiatePaymentRequest",
    "InitiatePaymentResponse",
    "PaymentStatsResponse",
    # Schedule
    "SessionStatus",
    "SessionRead",
    "SessionListResponse",
    "BookSessionRequest",
    "BookSessionResponse",
    "CancelBookingRequest",
    "CancelBookingResponse",
    "TrainerInfo",
    "ScheduleFilters",
    # Clubs
    "ClubSectionRead",
    "ClubTariffRead",
    "ClubRead",
    "ClubDetailRead",
    "ClubListResponse",
    "ClubLocationRead",
    "NearestClubResponse",
]
