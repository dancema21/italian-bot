"""Handler for /stats command."""
import logging
from collections import Counter
from telegram import Update
from telegram.ext import ContextTypes

from bot.utils.access import check_access
from bot.services.supabase import get_user_id, get_user_errors

logger = logging.getLogger(__name__)

CATEGORY_FR = {
    "conjugation": "Conjugaison",
    "agreement": "Accord",
    "vocabulary": "Vocabulaire",
    "prepositions": "Prépositions",
    "articles": "Articles",
    "spelling": "Orthographe",
    "word order": "Ordre des mots",
    "verb tense": "Temps verbaux",
    "pronouns": "Pronoms",
    "other": "Autre",
}


async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return

    telegram_id = update.effective_user.id
    user_id = get_user_id(telegram_id)
    if not user_id:
        await update.message.reply_text("Utilise /start pour t'enregistrer d'abord.")
        return

    errors = get_user_errors(user_id)
    total = len(errors)

    if total == 0:
        await update.message.reply_text(
            "📈 *Tes statistiques*\n\nAucune erreur enregistrée pour l'instant. Continue à t'entraîner !",
            parse_mode="Markdown"
        )
        return

    # Category breakdown
    category_counts = Counter(e["error_category"] for e in errors)
    sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)

    # Top 3 most frequent wrong phrases
    phrase_counts = Counter(e["wrong_phrase"] for e in errors)
    top_phrases = phrase_counts.most_common(3)

    # Build lookup wrong_phrase -> corrected_it (latest)
    phrase_correction = {}
    for e in errors:
        if e["wrong_phrase"] not in phrase_correction:
            phrase_correction[e["wrong_phrase"]] = e["corrected_phrase_it"]

    lines = [
        "📈 *Tes statistiques*\n",
        f"Total d'erreurs enregistrées : *{total}*\n",
        "*Par catégorie :*"
    ]
    for cat, count in sorted_categories:
        fr_cat = CATEGORY_FR.get(cat, cat)
        lines.append(f"  ⚠️ {fr_cat} — {count} erreur{'s' if count > 1 else ''}")

    lines.append("\n*Tes 3 erreurs les plus fréquentes :*")
    for i, (phrase, count) in enumerate(top_phrases, 1):
        corrected = phrase_correction.get(phrase, "?")
        lines.append(f"  {i}. {phrase} → {corrected}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
