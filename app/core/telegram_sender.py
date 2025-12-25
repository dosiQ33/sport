import httpx
import logging
from typing import Optional
from enum import Enum
from app.core.config import TELEGRAM_BOT_TOKEN_STAFF, TELEGRAM_BOT_TOKEN_STUDENT

logger = logging.getLogger(__name__)

class BotType(str, Enum):
    STAFF = "STAFF"
    STUDENT = "STUDENT"

async def send_telegram_message(
    chat_id: int, 
    text: str, 
    parse_mode: str = "HTML",
    bot_type: BotType = BotType.STAFF
) -> bool:
    """
    Send a message to a Telegram user.
    
    Args:
        chat_id: Telegram chat ID (user ID)
        text: Message text
        parse_mode: HTML or MarkdownV2
        bot_type: Which bot to use for sending (BotType.STAFF or BotType.STUDENT)
        
    Returns:
        bool: True if successful, False otherwise
    """
    token = TELEGRAM_BOT_TOKEN_STAFF if bot_type == BotType.STAFF else TELEGRAM_BOT_TOKEN_STUDENT
    
    if not token:
        logger.warning(f"Token for {bot_type} is not set. Cannot send notification.")
        return False
        
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=payload, timeout=10.0)
            
            if response.status_code == 200:
                return True
            else:
                logger.error(f"Failed to send Telegram message ({bot_type}): {response.text}")
                return False
                
    except Exception as e:
        logger.error(f"Error sending Telegram message ({bot_type}): {str(e)}")
        return False
