import re
from app.core.exceptions import ValidationError


def clean_phone_number(phone: str) -> str:
    """
    Очищает и валидирует номер телефона.
    Возвращает только цифры без '+' и других символов.
    """
    if not phone:
        raise ValidationError("Phone number cannot be empty")

    # Удаляем все кроме цифр
    clean_phone = re.sub(r"\D", "", phone)

    # Проверяем что остались только цифры
    if not clean_phone:
        raise ValidationError("Phone number must contain digits")

    # Проверяем длину (минимум 7, максимум 20 цифр)
    if len(clean_phone) < 7 or len(clean_phone) > 20:
        raise ValidationError("Phone number must be between 7 and 20 digits")

    # Проверяем что не начинается с 0
    if clean_phone.startswith("0"):
        raise ValidationError("Phone number cannot start with 0")

    return clean_phone
