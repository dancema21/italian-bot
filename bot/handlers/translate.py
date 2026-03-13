"""Handler for /traduire command."""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.utils.access import check_access
from bot.services import supabase as db
from bot.services.gemini import translate_word

logger = logging.getLogger(__name__)

# Pending translation data: telegram_id -> dict with fr/it phrases + original
_pending: dict = {}


async def traduire_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return

    text = " ".join(context.args).strip() if context.args else ""
    if not text:
        await update.message.reply_text(
            "Utilisation : /traduire <mot ou phrase>\n"
            "Exemple : /traduire salut"
        )
        return

    await update.message.reply_text("Traduction en cours... ⏳")

    try:
        result = await translate_word(text)
    except Exception as e:
        logger.error(f"translate_word failed: {e}")
        await update.message.reply_text("Erreur lors de la traduction. Réessaie.")
        return

    source_lang = result.get("source_lang", "fr")
    source_word = result.get("source_word", "")
    source_sentence = result.get("source_sentence", "")
    target_word = result.get("target_word", "")
    target_sentence = result.get("target_sentence", "")

    if source_lang == "fr":
        fr_word, fr_sentence = source_word, source_sentence
        it_word, it_sentence = target_word, target_sentence
        source_flag, target_flag = "🇫🇷", "🇮🇹"
    else:
        it_word, it_sentence = source_word, source_sentence
        fr_word, fr_sentence = target_word, target_sentence
        source_flag, target_flag = "🇮🇹", "🇫🇷"

    message = (
        f"{source_flag} {source_word}\n"
        f"{source_sentence}\n\n"
        f"{target_flag} {target_word}\n"
        f"{target_sentence}"
    )

    telegram_id = update.effective_user.id
    _pending[telegram_id] = {
        "original": text,
        "phrase_fr": f"{fr_word}\n{fr_sentence}",
        "phrase_it": f"{it_word}\n{it_sentence}",
    }

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("💾 Sauvegarder en flashcard", callback_data=f"tr_save:{telegram_id}"),
    ]])

    await update.message.reply_text(message, reply_markup=keyboard)


async def traduire_save_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return

    telegram_id = update.effective_user.id
    pending = _pending.pop(telegram_id, None)

    if not pending:
        await query.edit_message_reply_markup(None)
        await query.message.reply_text("Cette traduction a déjà été sauvegardée.")
        return

    user_id = db.get_user_id(telegram_id)
    if not user_id:
        await query.message.reply_text("Utilise /start pour t'enregistrer d'abord.")
        return

    success = db.save_translation_flashcard(
        user_id=user_id,
        original=pending["original"],
        phrase_fr=pending["phrase_fr"],
        phrase_it=pending["phrase_it"],
    )

    await query.edit_message_reply_markup(None)
    if success:
        await query.message.reply_text("✅ Flashcard sauvegardée !")
    else:
        await query.message.reply_text("Erreur lors de la sauvegarde. Réessaie.")
