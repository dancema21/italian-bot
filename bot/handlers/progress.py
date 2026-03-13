"""Handler for /progress command."""
import logging
from telegram import Update
from telegram.ext import ContextTypes

from bot.utils.access import check_access
from bot.services.supabase import get_user_id, get_all_topics, get_all_user_progress

logger = logging.getLogger(__name__)

LEVEL_EMOJI = {
    "A1": "🅰️ A1",
    "A2": "🅰️ A2",
    "B1": "🅱️ B1",
    "B2": "🅱️ B2",
}


async def progress_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return

    telegram_id = update.effective_user.id
    user_id = get_user_id(telegram_id)
    if not user_id:
        await update.message.reply_text("Utilise /start pour t'enregistrer d'abord.")
        return

    topics = get_all_topics()
    progress_records = get_all_user_progress(user_id)

    # Build lookup: topic_id -> session_count
    progress_map = {r["topic_id"]: r["session_count"] for r in progress_records}

    # Group topics by level
    levels = ["A1", "A2", "B1", "B2"]
    topics_by_level: dict[str, list] = {lvl: [] for lvl in levels}
    for topic in topics:
        lvl = topic["cefr_level"]
        if lvl in topics_by_level:
            topics_by_level[lvl].append(topic)

    lines = ["📊 *Ta progression*\n"]
    for lvl in levels:
        level_topics = topics_by_level[lvl]
        if not level_topics:
            continue
        lines.append(f"{LEVEL_EMOJI.get(lvl, lvl)}")
        for topic in level_topics:
            count = progress_map.get(topic["id"], 0)
            session_word = "session" if count <= 1 else "sessions"
            lines.append(f"  🇮🇹 {topic['title_fr']} — {count} {session_word}")
        lines.append("")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
