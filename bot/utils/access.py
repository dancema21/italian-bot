"""Whitelist access check helper."""
import logging
from bot.services.supabase import get_supabase

logger = logging.getLogger(__name__)

UNAUTHORIZED_MESSAGE = "Désolé, ce bot est privé. Tu n'es pas autorisé à l'utiliser."


async def is_allowed(telegram_id: int) -> bool:
    """Check if a telegram_id is in the allowed_users whitelist."""
    try:
        db = get_supabase()
        result = db.table("allowed_users").select("telegram_id").eq("telegram_id", telegram_id).execute()
        return len(result.data) > 0
    except Exception as e:
        logger.error(f"Error checking whitelist for {telegram_id}: {e}")
        return False


async def check_access(update, context) -> bool:
    """
    Check access and send unauthorized message if not allowed.
    Returns True if allowed, False otherwise.
    """
    telegram_id = update.effective_user.id
    allowed = await is_allowed(telegram_id)
    if not allowed:
        await update.effective_message.reply_text(UNAUTHORIZED_MESSAGE)
    return allowed
