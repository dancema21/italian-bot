"""Handler for /verbs command and tense selection flow."""
import logging
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.utils.access import check_access
from bot.utils.session import get_session, set_session, clear_session, update_session
from bot.services import supabase as db
from bot.services.gemini import (
    generate_scene,
    build_verbs_system_prompt,
    send_message,
    generate_recap,
    extract_errors,
    detect_vocabulary_usage,
)

logger = logging.getLogger(__name__)

TENSES = [
    ("Présent", "Presente"),
    ("Passé composé", "Passato prossimo"),
    ("Imparfait", "Imperfetto"),
    ("Futur simple", "Futuro semplice"),
    ("Conditionnel", "Condizionale"),
    ("Subjonctif présent", "Congiuntivo presente"),
    ("Subjonctif passé", "Congiuntivo passato"),
    ("Impératif", "Imperativo"),
]


async def verbs_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return

    # 2-column layout
    buttons = []
    for i in range(0, len(TENSES), 2):
        row = []
        for fr_label, it_label in TENSES[i:i + 2]:
            row.append(InlineKeyboardButton(fr_label, callback_data=f"verb_tense:{it_label}"))
        buttons.append(row)

    keyboard = InlineKeyboardMarkup(buttons)
    await update.message.reply_text("Choisis un temps verbal à pratiquer :", reply_markup=keyboard)


async def verb_tense_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return

    telegram_id = update.effective_user.id
    verb_focus = query.data.split(":", 1)[1]

    await query.edit_message_text(f"Génération d'une scène pour le *{verb_focus}*... ⏳", parse_mode="Markdown")

    user_id = db.upsert_user(
        telegram_id,
        update.effective_user.username,
        update.effective_user.first_name
    )

    # Use a general B1-level context with placeholder vocabulary for verb sessions
    placeholder_vocab = ["parlare", "essere", "avere", "fare", "andare", "venire", "dire", "sapere"]

    try:
        scene = await generate_scene(
            cefr_level="B1",
            topic_title_it=f"Pratica del {verb_focus}",
            vocabulary_sample=placeholder_vocab,
            verb_focus=verb_focus
        )
    except Exception as e:
        logger.error(f"Scene generation failed: {e}")
        await query.edit_message_text("Erreur lors de la génération de la scène. Réessaie.")
        return

    max_messages = random.randint(10, 15)
    session_number = db.get_completed_session_count(user_id, topic_id=None) + 1

    try:
        session_db_id = db.create_session(
            user_id=user_id,
            topic_id=None,
            session_number=session_number,
            generated_scene_prompt=scene["scene_prompt"],
            target_vocabulary=scene["target_vocabulary"],
            verb_focus=verb_focus
        )
    except Exception as e:
        logger.error(f"Session creation failed: {e}")
        await query.edit_message_text("Erreur lors de la création de la session. Réessaie.")
        return

    system_prompt = build_verbs_system_prompt(
        cefr_level="B1",
        verb_focus=verb_focus,
        generated_scene_prompt=scene["scene_prompt"],
        target_vocabulary=scene["target_vocabulary"],
        max_messages=max_messages
    )

    opening = scene["opening_line_it"]

    # Gemini requires history to start with a "user" turn.
    initial_history = [
        {"role": "user", "parts": ["[inizia la scena]"]},
        {"role": "model", "parts": [opening]},
    ]

    set_session(telegram_id, {
        "session_db_id": session_db_id,
        "topic_id": None,
        "topic_title_it": f"Pratica del {verb_focus}",
        "verb_focus": verb_focus,
        "target_vocabulary": scene["target_vocabulary"],
        "max_messages": max_messages,
        "message_count": 0,
        "conversation_history": initial_history,
        "errors_detected": [],
        "closing_triggered": False,
        "system_prompt": system_prompt,
        "user_id": user_id,
        "cefr_level": "B1",
        "vocabulary_used": [],
    })

    await query.edit_message_text(
        f"🇮🇹 *{verb_focus}* — Entraînement verbal\n\n"
        f"_(Envoie *END* à tout moment pour terminer la session et voir le récap)_",
        parse_mode="Markdown"
    )
    await context.bot.send_message(chat_id=update.effective_chat.id, text=opening)


async def verbs_conversation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle ongoing conversation messages during a /verbs session.
    This is the same logic as learn.py conversation_handler — both are
    registered in main.py with the same MessageHandler, so we delegate.
    """
    # Imported and reused from learn module
    from bot.handlers.learn import conversation_handler
    await conversation_handler(update, context)
