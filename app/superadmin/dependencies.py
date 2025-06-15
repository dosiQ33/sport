from fastapi import HTTPException, Header, status
import os

# Получаем токен SuperAdmin из переменной окружения
SUPERADMIN_TOKEN = os.getenv("SUPERADMIN_TOKEN")


def verify_superadmin_token(x_superadmin_token: str = Header(...)):
    """Проверка токена суперадмина"""
    if not SUPERADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SuperAdmin token not configured",
        )

    if x_superadmin_token != SUPERADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Invalid superadmin token"
        )
    return True
