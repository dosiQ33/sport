from typing import Dict, Any
from fastapi import Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import TELEGRAM_BOT_TOKEN, SUPERADMIN_TOKEN
from app.core.telegram_auth import TelegramAuth
from app.core.exceptions import (
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    TelegramAuthError,
)

security = HTTPBearer(
    scheme_name="Telegram InitData",
    description="Enter your Telegram Web App initData string",
)

# Проверяем наличие обязательных конфигураций
if not TELEGRAM_BOT_TOKEN:
    raise ConfigurationError("TELEGRAM_BOT_TOKEN", "Telegram bot token is required")

telegram_auth = TelegramAuth(TELEGRAM_BOT_TOKEN)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    """
    Dependency to get current authenticated user from Telegram initData.
    Returns user data if present, or full auth data if user not in initData.

    Usage in Swagger UI:
    1. Click "Authorize" button
    2. Enter your Telegram initData string in the "Value" field
    3. The initData should look like: "user=...&chat_instance=...&auth_date=...&hash=..."

    Raises:
        AuthenticationError: Если аутентификация не удалась
        TelegramAuthError: Если ошибка специфична для Telegram
    """
    try:
        init_data = credentials.credentials
        if not init_data or not init_data.strip():
            raise AuthenticationError("Authentication data is required")

        auth_data = telegram_auth.authenticate(init_data)

        # For backward compatibility, return user data if present
        if "user" in auth_data and auth_data["user"]:
            return auth_data["user"]

        # If no user data but auth was successful, return full auth data
        return auth_data

    except TelegramAuthError as e:
        # Уже наше исключение, просто перебрасываем
        raise e
    except Exception as e:
        # Преобразуем любую другую ошибку в TelegramAuthError
        raise TelegramAuthError(f"Telegram authentication failed: {str(e)}")


def verify_superadmin_token(x_superadmin_token: str = Header(...)):
    """
    Проверка токена суперадмина

    Raises:
        ConfigurationError: Если токен суперадмина не настроен
        AuthorizationError: Если токен неверный
    """
    if not SUPERADMIN_TOKEN:
        raise ConfigurationError(
            "SUPERADMIN_TOKEN", "SuperAdmin token not configured on server"
        )

    if not x_superadmin_token:
        raise AuthorizationError("SuperAdmin token header is required")

    if x_superadmin_token != SUPERADMIN_TOKEN:
        raise AuthorizationError("Invalid superadmin token")

    return True


# Альтернативная версия с более детальной информацией об ошибке
async def get_current_user_detailed(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    """
    Расширенная версия get_current_user с более детальной обработкой ошибок
    """
    try:
        init_data = credentials.credentials

        if not init_data:
            raise AuthenticationError(
                "Empty authentication data",
                details={"hint": "Please provide Telegram initData string"},
            )

        if not init_data.strip():
            raise AuthenticationError(
                "Invalid authentication data format",
                details={
                    "hint": "Authentication data cannot be empty or whitespace only"
                },
            )

        # Базовая валидация формата
        if "hash=" not in init_data:
            raise AuthenticationError(
                "Invalid initData format",
                details={"hint": "initData must contain hash parameter"},
            )

        auth_data = telegram_auth.authenticate(init_data)

        # Валидируем результат аутентификации
        if not isinstance(auth_data, dict):
            raise TelegramAuthError("Invalid authentication response format")

        # Проверяем наличие обязательных полей
        if "user" in auth_data:
            user_data = auth_data["user"]
            if not user_data.get("id"):
                raise TelegramAuthError("User ID is missing from authentication data")

            return user_data

        return auth_data

    except (AuthenticationError, TelegramAuthError):
        # Наши исключения - просто перебрасываем
        raise
    except Exception as e:
        # Любые другие ошибки преобразуем в TelegramAuthError
        raise TelegramAuthError(
            "Authentication processing failed", details={"original_error": str(e)}
        )


# Декораторы для разных уровней доступа
def require_authenticated_user():
    """Декоратор для endpoints, требующих аутентификации"""
    return Depends(get_current_user)


def require_superadmin():
    """Декоратор для endpoints, требующих права суперадмина"""
    return Depends(verify_superadmin_token)


# Хелпер функции для проверки ролей
def check_user_permission(user_data: dict, required_fields: list = None) -> bool:
    """
    Проверка базовых разрешений пользователя

    Args:
        user_data: Данные пользователя из аутентификации
        required_fields: Обязательные поля в данных пользователя

    Returns:
        bool: True если пользователь имеет необходимые разрешения

    Raises:
        AuthorizationError: Если пользователь не соответствует требованиям
    """
    if not user_data:
        raise AuthorizationError("User data is required")

    if not user_data.get("id"):
        raise AuthorizationError("User ID is missing")

    if required_fields:
        missing_fields = [
            field for field in required_fields if not user_data.get(field)
        ]
        if missing_fields:
            raise AuthorizationError(
                f"Missing required user fields: {', '.join(missing_fields)}",
                details={"missing_fields": missing_fields},
            )

    return True
