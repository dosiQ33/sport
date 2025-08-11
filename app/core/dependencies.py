from typing import Dict, Any
from fastapi import Depends, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import (
    TELEGRAM_BOT_TOKEN_STAFF,
    TELEGRAM_BOT_TOKEN_STUDENT,
    SUPERADMIN_TOKEN,
)
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

if not TELEGRAM_BOT_TOKEN_STAFF:
    raise ConfigurationError(
        "TELEGRAM_BOT_TOKEN_STAFF", "Staff telegram bot token is required"
    )

if not TELEGRAM_BOT_TOKEN_STUDENT:
    raise ConfigurationError(
        "TELEGRAM_BOT_TOKEN_STUDENT", "Student telegram bot token is required"
    )


telegram_auth_staff = TelegramAuth(TELEGRAM_BOT_TOKEN_STAFF)
telegram_auth_student = TelegramAuth(TELEGRAM_BOT_TOKEN_STUDENT)


async def get_current_staff_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    """Dependency для аутентификации staff пользователей"""
    try:
        init_data = credentials.credentials
        if not init_data or not init_data.strip():
            raise AuthenticationError("Authentication data is required")

        auth_data = telegram_auth_staff.authenticate(init_data)

        if "user" in auth_data and auth_data["user"]:
            return auth_data["user"]
        return auth_data

    except TelegramAuthError as e:
        raise e
    except Exception as e:
        raise TelegramAuthError(f"Staff telegram authentication failed: {str(e)}")


async def get_current_student_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> Dict[str, Any]:
    """Dependency для аутентификации student пользователей"""
    try:
        init_data = credentials.credentials
        if not init_data or not init_data.strip():
            raise AuthenticationError("Authentication data is required")

        auth_data = telegram_auth_student.authenticate(init_data)

        if "user" in auth_data and auth_data["user"]:
            return auth_data["user"]
        return auth_data

    except TelegramAuthError as e:
        raise e
    except Exception as e:
        raise TelegramAuthError(f"Student telegram authentication failed: {str(e)}")


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
