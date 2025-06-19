"""
Custom exceptions for the application
"""


class AppException(Exception):
    """Base exception for application-specific errors"""

    def __init__(self, message: str, error_code: str = None, details: dict = None):
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)


class BusinessLogicError(AppException):
    """Raised when business rules are violated"""

    def __init__(
        self,
        message: str,
        error_code: str = "BUSINESS_LOGIC_ERROR",
        details: dict = None,
    ):
        super().__init__(message, error_code, details)


class ResourceNotFoundError(AppException):
    """Raised when a requested resource is not found"""

    def __init__(
        self, message: str, error_code: str = "RESOURCE_NOT_FOUND", details: dict = None
    ):
        super().__init__(message, error_code, details)


class AuthenticationError(AppException):
    """Raised when authentication fails"""

    def __init__(
        self,
        message: str,
        error_code: str = "AUTHENTICATION_ERROR",
        details: dict = None,
    ):
        super().__init__(message, error_code, details)


class AuthorizationError(AppException):
    """Raised when user lacks permission for action"""

    def __init__(
        self,
        message: str,
        error_code: str = "AUTHORIZATION_ERROR",
        details: dict = None,
    ):
        super().__init__(message, error_code, details)


class ValidationError(AppException):
    """Raised when input validation fails"""

    def __init__(
        self, message: str, error_code: str = "VALIDATION_ERROR", details: dict = None
    ):
        super().__init__(message, error_code, details)


class DatabaseError(AppException):
    """Raised when database operation fails"""

    def __init__(
        self, message: str, error_code: str = "DATABASE_ERROR", details: dict = None
    ):
        super().__init__(message, error_code, details)


class ExternalServiceError(AppException):
    """Raised when external service (like Telegram API) fails"""

    def __init__(
        self,
        message: str,
        error_code: str = "EXTERNAL_SERVICE_ERROR",
        details: dict = None,
    ):
        super().__init__(message, error_code, details)


class RateLimitError(AppException):
    """Raised when rate limit is exceeded"""

    def __init__(
        self, message: str, error_code: str = "RATE_LIMIT_ERROR", details: dict = None
    ):
        super().__init__(message, error_code, details)


class ConfigurationError(AppException):
    """Raised when application configuration is invalid"""

    def __init__(
        self,
        message: str,
        error_code: str = "CONFIGURATION_ERROR",
        details: dict = None,
    ):
        super().__init__(message, error_code, details)


# Telegram-specific exceptions
class TelegramAuthError(AuthenticationError):
    """Custom exception for Telegram authentication errors"""

    pass
