from typing import Dict, Any
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import TELEGRAM_BOT_TOKEN
from app.core.telegram_auth import TelegramAuth

security = HTTPBearer(
    scheme_name="Telegram InitData",
    description="Enter your Telegram Web App initData string",
)

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
    """
    try:
        init_data = credentials.credentials
        auth_data = telegram_auth.authenticate(init_data)

        # For backward compatibility, return user data if present
        if "user" in auth_data and auth_data["user"]:
            return auth_data["user"]

        # If no user data but auth was successful, return full auth data
        return auth_data

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
