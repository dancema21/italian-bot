"""Handler for /notizie — read and discuss recent Italian news articles."""
from __future__ import annotations
import html
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.utils.access import check_access
from bot.services.gemini import search_italian_news, notizie_chat

logger = logging.getLogger(__name__)

# In-memory sessions: telegram_id -> state dict
notizie_sessions: dict = {}

_NAV = (
    "─────────────────\n"
    "/notizie — Lire et discuter un article\n"
    "/ciao — Session personnalisée par l'IA\n"
    "/learn — Nouvelle session par thème\n"
    "/verbs — Pratiquer un temps verbal\n"
    "/flashcards — Réviser tes erreurs\n"
    "/translate — Traduire un mot ou une phrase\n"
    "/progress — Ta progression\n"
    "/stats — Tes statistiques"
)


def is_in_notizie_session(telegram_id: int) -> bool:
    return telegram_id in notizie_sessions


async def notizie_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return

    telegram_id = update.effective_user.id
    await update.message.reply_text("🔍 Recherche des dernières actualités italiennes...")

    try:
        articles = await search_italian_news()
    except Exception as e:
        logger.error(f"search_italian_news failed: {e}")
        await update.message.reply_text(
            "Impossible de récupérer les actualités pour le moment. Réessaie dans quelques instants."
        )
        return

    if not articles:
        await update.message.reply_text(
            "Aucun article valide trouvé pour le moment. Réessaie dans quelques instants."
        )
        return

    notizie_sessions[telegram_id] = {
        "state": "selecting",
        "articles": articles,
    }

    buttons = []
    for i, article in enumerate(articles):
        title = article.get("title", "")
        source = article.get("source", "")
        label = f"📰 {title[:45]}{'…' if len(title) > 45 else ''} — {source}"
        buttons.append([InlineKeyboardButton(label, callback_data=f"nz_topic:{i}")])

    await update.message.reply_text(
        "Choisis un article à lire et à discuter en italien :",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def notizie_topic_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if not await check_access(update, context):
        return

    telegram_id = update.effective_user.id
    session = notizie_sessions.get(telegram_id)
    if not session:
        await query.edit_message_text("Session expirée. Utilise /notizie pour recommencer.")
        return

    idx = int(query.data.split(":")[1])
    articles = session.get("articles", [])
    if idx >= len(articles):
        return

    article = articles[idx]
    notizie_sessions[telegram_id] = {
        "state": "reading",
        "article": article,
        "conversation_history": [],
        "message_count": 0,
    }

    await query.edit_message_text(
        f"📰 <b>{html.escape(article.get('title', ''))}</b>\n"
        f"<i>{html.escape(article.get('source', ''))}</i>\n\n"
        f"{html.escape(article.get('summary_fr', ''))}\n\n"
        f"🔗 {article.get('url', '')}\n\n"
        "Prends le temps de lire l'article. "
        "Quand tu es prêt à en discuter en italien, envoie <b>pronto</b> 🇮🇹\n"
        "<i>(ou envoie END à tout moment pour terminer)</i>",
        parse_mode="HTML",
    )


async def notizie_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Called from text_message_router when user is in a notizie session."""
    if not await check_access(update, context):
        return

    telegram_id = update.effective_user.id
    session = notizie_sessions.get(telegram_id)
    if not session:
        return

    user_text = update.message.text.strip()

    if user_text.upper() == "END":
        notizie_sessions.pop(telegram_id, None)
        await update.message.reply_text("Discussion terminée. Bonne continuation ! 🇮🇹")
        await update.message.reply_text(_NAV)
        return

    state = session["state"]

    if state == "reading":
        await _start_discussion(update, telegram_id, session)
    elif state == "discussing":
        await _continue_discussion(update, telegram_id, session, user_text)


async def _start_discussion(update: Update, telegram_id: int, session: dict):
    """Generate the first comprehension question and transition to discussing state."""
    article = session["article"]

    try:
        first_question = await notizie_chat(
            article=article,
            conversation_history=[],
            user_message="[inizia la discussione sull'articolo]",
            message_count=0,
        )
    except Exception as e:
        logger.error(f"notizie_chat failed: {e}")
        await update.message.reply_text("Erreur lors du démarrage de la discussion. Réessaie.")
        return

    session["state"] = "discussing"
    session["conversation_history"] = [
        {"role": "user", "parts": ["[inizia la discussione sull'articolo]"]},
        {"role": "model", "parts": [first_question]},
    ]
    session["message_count"] = 0

    await update.message.reply_text(first_question)


async def _continue_discussion(
    update: Update, telegram_id: int, session: dict, user_text: str
):
    session["message_count"] += 1

    try:
        reply = await notizie_chat(
            article=session["article"],
            conversation_history=session["conversation_history"],
            user_message=user_text,
            message_count=session["message_count"],
        )
    except Exception as e:
        logger.error(f"notizie_chat failed: {e}")
        await update.message.reply_text("Erreur de connexion. Réessaie.")
        return

    session["conversation_history"].append({"role": "user", "parts": [user_text]})
    session["conversation_history"].append({"role": "model", "parts": [reply]})

    await update.message.reply_text(reply)
