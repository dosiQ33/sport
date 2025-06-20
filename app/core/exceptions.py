"""
Пользовательские исключения для централизованной обработки ошибок
"""

from typing import Optional, Dict, Any


class BaseAppException(Exception):
    """Базовое исключение приложения"""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code or self.__class__.__name__
        self.details = details or {}
        super().__init__(self.message)


# === Ошибки аутентификации ===
class AuthenticationError(BaseAppException):
    """Ошибка аутентификации"""

    def __init__(
        self,
        message: str = "Authentication failed",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, 401, "AUTHENTICATION_ERROR", details)


class AuthorizationError(BaseAppException):
    """Ошибка авторизации"""

    def __init__(
        self, message: str = "Access denied", details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message, 403, "AUTHORIZATION_ERROR", details)


# === Ошибки валидации ===
class ValidationError(BaseAppException):
    """Ошибка валидации данных"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, 400, "VALIDATION_ERROR", details)


class DuplicateError(BaseAppException):
    """Ошибка дублирования данных"""

    def __init__(self, resource: str, field: str, value: str):
        message = f"{resource} with {field} '{value}' already exists"
        details = {"resource": resource, "field": field, "value": value}
        super().__init__(message, 409, "DUPLICATE_ERROR", details)


# === Ошибки ресурсов ===
class NotFoundError(BaseAppException):
    """Ресурс не найден"""

    def __init__(self, resource: str, identifier: str = None):
        if identifier:
            message = f"{resource} with identifier '{identifier}' not found"
            details = {"resource": resource, "identifier": identifier}
        else:
            message = f"{resource} not found"
            details = {"resource": resource}
        super().__init__(message, 404, "NOT_FOUND", details)


# === Бизнес-логика ===
class BusinessLogicError(BaseAppException):
    """Ошибка бизнес-логики"""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, 400, "BUSINESS_LOGIC_ERROR", details)


class LimitExceededError(BusinessLogicError):
    """Превышен лимит"""

    def __init__(self, resource: str, limit: int, current: int):
        message = f"{resource} limit exceeded: {current}/{limit}"
        details = {"resource": resource, "limit": limit, "current": current}
        super().__init__(message, details)


class PermissionDeniedError(BaseAppException):
    """Отказано в доступе к ресурсу"""

    def __init__(self, action: str, resource: str, reason: str = None):
        message = f"Permission denied: cannot {action} {resource}"
        if reason:
            message += f" - {reason}"
        details = {"action": action, "resource": resource, "reason": reason}
        super().__init__(message, 403, "PERMISSION_DENIED", details)


# === Ошибки базы данных ===
class DatabaseError(BaseAppException):
    """Ошибка базы данных"""

    def __init__(
        self,
        message: str = "Database operation failed",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, 500, "DATABASE_ERROR", details)


class DatabaseConnectionError(BaseAppException):
    """Ошибка подключения к базе данных"""

    def __init__(self, message: str = "Database connection failed"):
        super().__init__(message, 503, "DATABASE_CONNECTION_ERROR")


class DatabaseTimeoutError(BaseAppException):
    """Таймаут операции с базой данных"""

    def __init__(self, operation: str, timeout: int):
        message = f"Database operation '{operation}' timed out after {timeout}s"
        details = {"operation": operation, "timeout": timeout}
        super().__init__(message, 504, "DATABASE_TIMEOUT", details)


class DatabaseIntegrityError(BaseAppException):
    """Ошибка целостности данных"""

    def __init__(self, constraint: str, details: Optional[Dict[str, Any]] = None):
        message = f"Database integrity constraint violated: {constraint}"
        error_details = {"constraint": constraint}
        if details:
            error_details.update(details)
        super().__init__(message, 409, "DATABASE_INTEGRITY_ERROR", error_details)


# === Ошибки внешних сервисов ===
class ExternalServiceError(BaseAppException):
    """Ошибка внешнего сервиса"""

    def __init__(self, service: str, message: str = None):
        message = message or f"External service '{service}' error"
        details = {"service": service}
        super().__init__(message, 502, "EXTERNAL_SERVICE_ERROR", details)


class TelegramAuthError(ExternalServiceError):
    """Ошибка аутентификации Telegram"""

    def __init__(self, message: str = "Telegram authentication failed"):
        super().__init__("telegram", message)


# === Ошибки конфигурации ===
class ConfigurationError(BaseAppException):
    """Ошибка конфигурации"""

    def __init__(self, parameter: str, message: str = None):
        message = (
            message or f"Configuration parameter '{parameter}' is invalid or missing"
        )
        details = {"parameter": parameter}
        super().__init__(message, 500, "CONFIGURATION_ERROR", details)
