"""Handler for /flashcards command."""
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.utils.access import check_access
from bot.services.supabase import get_user_id, get_due_flashcards, update_flashcard
from bot.services.sm2 import sm2_update

logger = logging.getLogger(__name__)

# In-memory state for ongoing flashcard reviews: telegram_id -> state dict
flashcard_sessions: dict = {}


async def flashcards_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return

    telegram_id = update.effective_user.id
    user_id = get_user_id(telegram_id)
    if not user_id:
        await update.message.reply_text("Utilise /start pour t'enregistrer d'abord.")
        return

    due_cards = get_due_flashcards(user_id)
    if not due_cards:
        await update.message.reply_text("Aucune carte à réviser aujourd'hui 🎉 Reviens demain !")
        return

    flashcard_sessions[telegram_id] = {
        "cards": due_cards,
        "index": 0,
        "reviewed": 0,
    }

    await _show_card(update.message, telegram_id)


async def _show_card(message, telegram_id: int):
    """Show the French side of the card with a 'Voir la réponse' button."""
    state = flashcard_sessions.get(telegram_id)
    if not state:
        return

    cards = state["cards"]
    idx = state["index"]

    if idx >= len(cards):
        reviewed = state["reviewed"]
        del flashcard_sessions[telegram_id]
        await message.reply_text(
            f"{reviewed} carte{'s' if reviewed > 1 else ''} révisée{'s' if reviewed > 1 else ''} aujourd'hui ✅"
        )
        return

    card = cards[idx]
    error_data = card.get("errors", {})
    fr_phrase = error_data.get("corrected_phrase_fr", "?")
    total = len(cards)
    progress = f"{idx + 1}/{total}"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("👁 Voir la réponse", callback_data=f"fc_reveal:{card['id']}"),
    ]])

    await message.reply_text(
        f"Carte {progress}\n\n🇫🇷 {fr_phrase}",
        reply_markup=keyboard,
    )


async def flashcard_reveal_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reveal the Italian answer and show rating buttons."""
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return

    telegram_id = update.effective_user.id
    state = flashcard_sessions.get(telegram_id)
    if not state:
        await query.edit_message_reply_markup(None)
        return

    card_id = int(query.data.split(":")[1])
    cards = state["cards"]
    idx = state["index"]
    card = cards[idx]

    if card["id"] != card_id:
        return

    error_data = card.get("errors", {})
    fr_phrase = error_data.get("corrected_phrase_fr", "?")
    it_phrase = error_data.get("corrected_phrase_it", "?")
    total = len(cards)
    progress = f"{idx + 1}/{total}"

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Correct", callback_data=f"fc_rate:correct:{card_id}"),
        InlineKeyboardButton("❌ Incorrect", callback_data=f"fc_rate:incorrect:{card_id}"),
    ]])

    await query.edit_message_text(
        f"Carte {progress}\n\n🇫🇷 {fr_phrase}\n\n🇮🇹 {it_phrase}\n\nC'était correct ?",
        reply_markup=keyboard,
    )


async def flashcard_rating_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle correct/incorrect rating, apply SM-2, move to next card."""
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return

    telegram_id = update.effective_user.id
    state = flashcard_sessions.get(telegram_id)
    if not state:
        await query.edit_message_reply_markup(None)
        return

    parts = query.data.split(":")
    if len(parts) != 3:
        return

    rating_str = parts[1]
    card_id = int(parts[2])

    cards = state["cards"]
    idx = state["index"]
    card = cards[idx]

    if card["id"] != card_id:
        return

    quality = 5 if rating_str == "correct" else 1
    new_ef, new_interval, new_reps = sm2_update(
        card["easiness_factor"],
        card["interval_days"],
        card["repetitions"],
        quality,
    )
    update_flashcard(card_id, new_ef, new_interval, new_reps)

    state["index"] += 1
    state["reviewed"] += 1

    await query.edit_message_reply_markup(None)
    await _show_card(query.message, telegram_id)


# No message handler needed anymore — flashcards are fully button-driven
flashcard_message_handler = None
