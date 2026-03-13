"""Handler for /learn command and topic selection flow."""
import logging
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.utils.access import check_access
from bot.utils.session import get_session, set_session, clear_session, update_session
from bot.services import supabase as db
from bot.services.gemini import (
    generate_scene,
    build_learn_system_prompt,
    send_message,
    generate_recap,
    extract_errors,
    extract_vocab_tips,
    detect_vocabulary_usage,
    transcribe_voice,
)

logger = logging.getLogger(__name__)

CEFR_LEVELS = ["A1", "A2", "B1", "B2"]

NO_SESSION_MESSAGE = "Utilise /learn pour commencer une session ou /help pour voir les commandes disponibles."

# Italian farewell phrases that signal the LLM is closing the scene
_CLOSING_PHRASES = [
    "arrivederci", "a presto", "ci vediamo", "devo andare", "devo scappare",
    "ho un appuntamento", "mi devo andare", "buona giornata", "buona serata",
    "buona fortuna", "addio", "a domani", "a dopo",
]


def _is_closing_message(text: str) -> bool:
    """Return True if the LLM reply contains a farewell/closing phrase."""
    lower = text.lower()
    return any(phrase in lower for phrase in _CLOSING_PHRASES)


async def learn_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("A1", callback_data="learn_level:A1"),
            InlineKeyboardButton("A2", callback_data="learn_level:A2"),
            InlineKeyboardButton("B1", callback_data="learn_level:B1"),
            InlineKeyboardButton("B2", callback_data="learn_level:B2"),
        ]
    ])
    await update.message.reply_text("Choisis ton niveau :", reply_markup=keyboard)


async def learn_level_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return

    telegram_id = update.effective_user.id
    level = query.data.split(":")[1]

    user_id = db.get_user_id(telegram_id)
    if not user_id:
        db.upsert_user(telegram_id, update.effective_user.username, update.effective_user.first_name)
        user_id = db.get_user_id(telegram_id)

    topics = db.get_topics_by_level(level)
    if not topics:
        await query.edit_message_text("Aucun thème disponible pour ce niveau.")
        return

    buttons = []
    for topic in topics:
        count = db.get_session_count(user_id, topic["id"])
        label = f"🇮🇹 {topic['title_fr']} — {count} fois"
        buttons.append([InlineKeyboardButton(label, callback_data=f"learn_topic:{topic['id']}")])

    keyboard = InlineKeyboardMarkup(buttons)
    await query.edit_message_text(f"Niveau {level} — Choisis un thème :", reply_markup=keyboard)


async def learn_topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return

    telegram_id = update.effective_user.id
    topic_id = int(query.data.split(":")[1])

    await query.edit_message_text("Génération de la scène en cours... ⏳")

    topic = db.get_topic(topic_id)
    if not topic:
        await query.edit_message_text("Thème introuvable.")
        return

    user_id = db.upsert_user(
        telegram_id,
        update.effective_user.username,
        update.effective_user.first_name
    )

    vocabulary = topic["vocabulary"]
    cefr_level = topic["cefr_level"]

    try:
        scene = await generate_scene(
            cefr_level=cefr_level,
            topic_title_it=topic["title_it"],
            vocabulary_sample=vocabulary,
        )
    except Exception as e:
        logger.error(f"Scene generation failed: {e}")
        await query.edit_message_text("Erreur lors de la génération de la scène. Réessaie.")
        return

    max_messages = random.randint(10, 15)
    session_number = db.get_completed_session_count(user_id, topic_id) + 1

    try:
        session_db_id = db.create_session(
            user_id=user_id,
            topic_id=topic_id,
            session_number=session_number,
            generated_scene_prompt=scene["scene_prompt"],
            target_vocabulary=scene["target_vocabulary"],
            verb_focus=None
        )
    except Exception as e:
        logger.error(f"Session creation failed: {e}")
        await query.edit_message_text("Erreur lors de la création de la session. Réessaie.")
        return

    system_prompt = build_learn_system_prompt(
        cefr_level=cefr_level,
        topic_title_it=topic["title_it"],
        generated_scene_prompt=scene["scene_prompt"],
        target_vocabulary=scene["target_vocabulary"],
        max_messages=max_messages
    )

    opening = scene["opening_line_it"]

    # Gemini requires history to start with a "user" turn.
    # We seed it with a silent trigger so the opening line is already in context
    # when the user sends their first real message.
    initial_history = [
        {"role": "user", "parts": ["[inizia la scena]"]},
        {"role": "model", "parts": [opening]},
    ]

    set_session(telegram_id, {
        "session_db_id": session_db_id,
        "topic_id": topic_id,
        "topic_title_it": topic["title_it"],
        "verb_focus": None,
        "target_vocabulary": scene["target_vocabulary"],
        "max_messages": max_messages,
        "message_count": 0,
        "conversation_history": initial_history,
        "errors_detected": [],
        "closing_triggered": False,
        "system_prompt": system_prompt,
        "user_id": user_id,
        "cefr_level": cefr_level,
        "vocabulary_used": [],
    })

    # Show topic header, then send opening line as a new message
    await query.edit_message_text(
        f"🇮🇹 *{topic['title_fr']}* — Niveau {cefr_level}\n\n"
        f"_(Envoie *END* à tout moment pour terminer la session et voir le récap)_",
        parse_mode="Markdown"
    )
    await context.bot.send_message(chat_id=update.effective_chat.id, text=opening)


async def _process_user_input(update: Update, telegram_id: int, session: dict, user_text: str):
    """Core conversation logic — shared by text and voice handlers."""
    if user_text.strip().upper() == "END":
        await _trigger_recap(update, telegram_id, session)
        return

    session["message_count"] += 1
    message_count = session["message_count"]

    # Track vocabulary usage
    used = detect_vocabulary_usage(user_text, session["target_vocabulary"])
    for w in used:
        if w not in session["vocabulary_used"]:
            session["vocabulary_used"].append(w)

    # Append user message to history
    session["conversation_history"].append({"role": "user", "parts": [user_text]})

    closing_hint = False
    if message_count >= session["max_messages"] - 2 and not session["closing_triggered"]:
        closing_hint = True
        session["closing_triggered"] = True

    try:
        reply = await send_message(
            system_prompt=session["system_prompt"],
            conversation_history=session["conversation_history"][:-1],
            user_message=user_text,
            closing_hint=closing_hint
        )
    except Exception as e:
        logger.error(f"Gemini send_message failed: {e}")
        await update.message.reply_text("Erreur de connexion au modèle. Réessaie.")
        return

    clean_reply, errors = extract_errors(reply)
    session["errors_detected"].extend(errors)
    session["conversation_history"].append({"role": "model", "parts": [clean_reply]})

    try:
        db.update_session_message_count(session["session_db_id"], message_count)
    except Exception as e:
        logger.error(f"update_session_message_count failed: {e}")

    await update.message.reply_text(clean_reply)

    if message_count >= session["max_messages"] or _is_closing_message(clean_reply):
        await _trigger_recap(update, telegram_id, session)


async def conversation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages during an active session."""
    if not await check_access(update, context):
        return

    telegram_id = update.effective_user.id
    session = get_session(telegram_id)

    if not session:
        await update.message.reply_text(NO_SESSION_MESSAGE)
        return

    await _process_user_input(update, telegram_id, session, update.message.text)


async def _trigger_recap(update: Update, telegram_id: int, session: dict):
    """Generate recap, save to DB, clear session."""
    await update.message.reply_text("Un instant, je prépare le récapitulatif... ⏳")

    # Extract actual user messages (skip the silent [inizia la scena] seed)
    user_messages = [
        turn["parts"][0]
        for turn in session["conversation_history"]
        if turn["role"] == "user" and turn["parts"][0] != "[inizia la scena]"
    ]

    try:
        recap_raw = await generate_recap(
            errors=session["errors_detected"],
            target_vocabulary=session["target_vocabulary"],
            vocabulary_used=session["vocabulary_used"],
            user_messages=user_messages,
        )
    except Exception as e:
        logger.error(f"generate_recap failed: {e}")
        recap_raw = "Erreur lors de la génération du récapitulatif."

    recap, vocab_tips = extract_vocab_tips(recap_raw)
    await update.message.reply_text(recap)
    await update.message.reply_text(
        "─────────────────\n"
        "/learn — Nouvelle session par thème\n"
        "/verbs — Pratiquer un temps verbal\n"
        "/flashcards — Réviser tes erreurs\n"
        "/traduire — Traduire un mot ou une phrase\n"
        "/progress — Ta progression\n"
        "/stats — Tes statistiques"
    )

    # Save errors and create flashcards
    try:
        error_ids = db.save_errors(
            session_id=session["session_db_id"],
            user_id=session["user_id"],
            topic_id=session["topic_id"],
            errors=session["errors_detected"]
        )
        db.create_flashcards(session["user_id"], error_ids)
    except Exception as e:
        logger.error(f"Error saving session data: {e}")

    # Save vocabulary tips as flashcards
    if vocab_tips:
        try:
            tip_errors = [
                {
                    "wrong": tip["original"],
                    "corrected_it": tip["phrase_it"],
                    "corrected_fr": tip["phrase_fr"],
                    "category": "vocabulary_tip",
                }
                for tip in vocab_tips
                if tip.get("phrase_it") and tip.get("phrase_fr")
            ]
            tip_ids = db.save_errors(
                session_id=session["session_db_id"],
                user_id=session["user_id"],
                topic_id=session["topic_id"],
                errors=tip_errors,
            )
            db.create_flashcards(session["user_id"], tip_ids)
        except Exception as e:
            logger.error(f"Error saving vocab tip flashcards: {e}")

    # Update topic progress (only for /learn sessions with a topic)
    if session["topic_id"] is not None:
        try:
            db.upsert_topic_progress(session["user_id"], session["topic_id"])
        except Exception as e:
            logger.error(f"upsert_topic_progress failed: {e}")

    # Mark session complete
    try:
        db.complete_session(session["session_db_id"])
    except Exception as e:
        logger.error(f"complete_session failed: {e}")

    clear_session(telegram_id)


async def voice_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Transcribe a voice note and feed it into the active conversation."""
    if not await check_access(update, context):
        return

    telegram_id = update.effective_user.id
    session = get_session(telegram_id)

    if not session:
        await update.message.reply_text(NO_SESSION_MESSAGE)
        return

    voice = update.message.voice
    try:
        file = await context.bot.get_file(voice.file_id)
        audio_bytes = bytes(await file.download_as_bytearray())
    except Exception as e:
        logger.error(f"Voice download failed: {e}")
        await update.message.reply_text("Impossible de télécharger le message vocal. Réessaie.")
        return

    try:
        transcription = await transcribe_voice(audio_bytes, mime_type="audio/ogg")
    except Exception as e:
        logger.error(f"Transcription failed: {e}")
        await update.message.reply_text("Impossible de transcrire le message vocal. Réessaie.")
        return

    # Echo the transcription so the user can see what was understood
    await update.message.reply_text(f"🎙 {transcription}")

    await _process_user_input(update, telegram_id, session, transcription)
