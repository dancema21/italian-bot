"""Handler for /start command."""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from bot.utils.access import check_access
from bot.services.supabase import upsert_user

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = """Benvenuto / Bienvenue ! 🇮🇹

Je suis ton assistant pour apprendre l'italien. Voici ce que tu peux faire :

/learn — Commencer une session de conversation par thème
/verbs — Pratiquer un temps verbal spécifique
/flashcards — Réviser tes erreurs avec des cartes mémoire
/progress — Voir ta progression par thème
/stats — Voir tes statistiques d'erreurs
/help — Afficher cette aide"""


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return

    user = update.effective_user
    try:
        upsert_user(user.id, user.username, user.first_name)
    except Exception as e:
        logger.error(f"Failed to upsert user {user.id}: {e}")

    await update.message.reply_text(WELCOME_MESSAGE)


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return
    await update.message.reply_text(WELCOME_MESSAGE)
