"""Entry point — registers all handlers and starts the bot."""
import logging
import os
from dotenv import load_dotenv

load_dotenv()

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from bot.handlers.start import start_handler, help_handler
from bot.handlers.learn import (
    learn_handler,
    learn_level_callback,
    learn_topic_callback,
    conversation_handler,
    voice_handler,
)
from bot.handlers.verbs import verbs_handler, verb_tense_callback
from bot.handlers.flashcards import (
    flashcards_handler,
    flashcard_reveal_callback,
    flashcard_rating_callback,
    flashcard_sessions,
)
from bot.handlers.progress import progress_handler
from bot.handlers.stats import stats_handler
from bot.handlers.translate import traduire_handler, traduire_save_callback
from bot.utils.session import get_session

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def text_message_router(update: Update, context):
    """
    Route incoming text messages based on user state:
    1. Active conversation session (learn / verbs)
    2. Default: show help hint
    """
    telegram_id = update.effective_user.id if update.effective_user else None
    if not telegram_id:
        return

    # Active conversation session
    if get_session(telegram_id) is not None:
        await conversation_handler(update, context)
        return

    # Default: no active session
    await update.message.reply_text(
        "Utilise /learn pour commencer une session ou /help pour voir les commandes disponibles."
    )


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = Application.builder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("learn", learn_handler))
    app.add_handler(CommandHandler("verbs", verbs_handler))
    app.add_handler(CommandHandler("flashcards", flashcards_handler))
    app.add_handler(CommandHandler("progress", progress_handler))
    app.add_handler(CommandHandler("stats", stats_handler))
    app.add_handler(CommandHandler("traduire", traduire_handler))

    # Callback queries
    app.add_handler(CallbackQueryHandler(learn_level_callback, pattern=r"^learn_level:"))
    app.add_handler(CallbackQueryHandler(learn_topic_callback, pattern=r"^learn_topic:"))
    app.add_handler(CallbackQueryHandler(verb_tense_callback, pattern=r"^verb_tense:"))
    app.add_handler(CallbackQueryHandler(flashcard_reveal_callback, pattern=r"^fc_reveal:"))
    app.add_handler(CallbackQueryHandler(flashcard_rating_callback, pattern=r"^fc_rate:"))
    app.add_handler(CallbackQueryHandler(traduire_save_callback, pattern=r"^tr_save:"))

    # Text message router
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_router)
    )

    # Voice message handler (active sessions only)
    app.add_handler(
        MessageHandler(filters.VOICE, voice_handler)
    )

    logger.info("Bot starting...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
