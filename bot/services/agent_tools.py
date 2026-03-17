"""Tool functions for the /ciao agent loop — all query Supabase directly."""
from __future__ import annotations
import logging

from bot.services.supabase import get_supabase

logger = logging.getLogger(__name__)


def get_recent_errors(user_id: int) -> list[dict]:
    """Last 20 errors from session_errors."""
    try:
        db = get_supabase()
        result = (
            db.table("session_errors")
            .select("wrong, correct, category, topic")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        return result.data
    except Exception as e:
        logger.warning(f"get_recent_errors failed: {e}")
        return []


def get_flashcard_performance(user_id: int) -> list[dict]:
    """All flashcards ordered by easiness_factor ascending (lowest = most difficult)."""
    try:
        db = get_supabase()
        result = (
            db.table("flashcards")
            .select("easiness_factor, repetitions, errors(corrected_phrase_it, error_category)")
            .eq("user_id", user_id)
            .order("easiness_factor")
            .limit(20)
            .execute()
        )
        return [
            {
                "phrase": row.get("errors", {}).get("corrected_phrase_it", ""),
                "category": row.get("errors", {}).get("error_category", ""),
                "easiness_factor": row["easiness_factor"],
                "repetitions": row["repetitions"],
            }
            for row in result.data
            if row.get("errors")
        ]
    except Exception as e:
        logger.warning(f"get_flashcard_performance failed: {e}")
        return []


def get_session_history(user_id: int) -> list[dict]:
    """Completed /learn sessions grouped by topic with count and last trained date."""
    try:
        db = get_supabase()
        result = (
            db.table("sessions")
            .select("topics(title_it, cefr_level), started_at")
            .eq("user_id", user_id)
            .eq("is_completed", True)
            .order("started_at", desc=True)
            .limit(50)
            .execute()
        )
        grouped: dict = {}
        for row in result.data:
            topic = row.get("topics")
            if not topic:
                continue
            key = topic["title_it"]
            if key not in grouped:
                grouped[key] = {
                    "topic": key,
                    "cefr_level": topic["cefr_level"],
                    "count": 0,
                    "last_seen": row["started_at"],
                }
            grouped[key]["count"] += 1
        return list(grouped.values())
    except Exception as e:
        logger.warning(f"get_session_history failed: {e}")
        return []


def get_topic_list() -> list[dict]:
    """All available topics with their CEFR levels."""
    try:
        db = get_supabase()
        result = (
            db.table("topics")
            .select("cefr_level, title_it")
            .order("cefr_level")
            .order("id")
            .execute()
        )
        return result.data
    except Exception as e:
        logger.warning(f"get_topic_list failed: {e}")
        return []
