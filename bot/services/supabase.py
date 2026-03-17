"""All database operations via Supabase."""
from __future__ import annotations
import logging
import os
from datetime import datetime, timezone, timedelta
from supabase import create_client, Client

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_supabase() -> Client:
    global _client
    if _client is None:
        url = os.environ["SUPABASE_URL"]
        key = os.environ["SUPABASE_ANON_KEY"]
        _client = create_client(url, key)
    return _client


# ── Users ──────────────────────────────────────────────────────────────────

def upsert_user(telegram_id: int, username: str | None, first_name: str | None) -> int:
    """Insert or fetch user; returns internal user id."""
    try:
        db = get_supabase()
        result = db.table("users").upsert(
            {"telegram_id": telegram_id, "username": username, "first_name": first_name},
            on_conflict="telegram_id"
        ).execute()
        return result.data[0]["id"]
    except Exception as e:
        logger.error(f"upsert_user error: {e}")
        raise


def get_user_id(telegram_id: int) -> int | None:
    """Return internal user id for a telegram_id, or None."""
    try:
        db = get_supabase()
        result = db.table("users").select("id").eq("telegram_id", telegram_id).execute()
        if result.data:
            return result.data[0]["id"]
        return None
    except Exception as e:
        logger.error(f"get_user_id error: {e}")
        return None


# ── Topics ─────────────────────────────────────────────────────────────────

def get_topics_by_level(cefr_level: str) -> list[dict]:
    try:
        db = get_supabase()
        result = db.table("topics").select("*").eq("cefr_level", cefr_level).order("id").execute()
        return result.data
    except Exception as e:
        logger.error(f"get_topics_by_level error: {e}")
        return []


def get_topic(topic_id: int) -> dict | None:
    try:
        db = get_supabase()
        result = db.table("topics").select("*").eq("id", topic_id).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"get_topic error: {e}")
        return None


def get_all_topics() -> list[dict]:
    try:
        db = get_supabase()
        result = db.table("topics").select("*").order("cefr_level").order("id").execute()
        return result.data
    except Exception as e:
        logger.error(f"get_all_topics error: {e}")
        return []


# ── Topic Progress ──────────────────────────────────────────────────────────

def get_user_topic_progress(user_id: int, topic_id: int) -> dict | None:
    try:
        db = get_supabase()
        result = (
            db.table("user_topic_progress")
            .select("*")
            .eq("user_id", user_id)
            .eq("topic_id", topic_id)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        logger.error(f"get_user_topic_progress error: {e}")
        return None


def get_all_user_progress(user_id: int) -> list[dict]:
    try:
        db = get_supabase()
        result = (
            db.table("user_topic_progress")
            .select("topic_id, session_count, last_trained_at")
            .eq("user_id", user_id)
            .execute()
        )
        return result.data
    except Exception as e:
        logger.error(f"get_all_user_progress error: {e}")
        return []


def upsert_topic_progress(user_id: int, topic_id: int):
    """Increment session_count and update last_trained_at."""
    try:
        db = get_supabase()
        existing = get_user_topic_progress(user_id, topic_id)
        if existing:
            db.table("user_topic_progress").update({
                "session_count": existing["session_count"] + 1,
                "last_trained_at": datetime.now(timezone.utc).isoformat()
            }).eq("user_id", user_id).eq("topic_id", topic_id).execute()
        else:
            db.table("user_topic_progress").insert({
                "user_id": user_id,
                "topic_id": topic_id,
                "session_count": 1,
                "last_trained_at": datetime.now(timezone.utc).isoformat()
            }).execute()
    except Exception as e:
        logger.error(f"upsert_topic_progress error: {e}")


def get_session_count(user_id: int, topic_id: int) -> int:
    """Return completed session count for user+topic."""
    progress = get_user_topic_progress(user_id, topic_id)
    return progress["session_count"] if progress else 0


# ── Sessions ───────────────────────────────────────────────────────────────

def create_session(
    user_id: int,
    topic_id: int | None,
    session_number: int,
    generated_scene_prompt: str,
    target_vocabulary: list,
    verb_focus: str | None
) -> int:
    """Create a session record and return its id."""
    try:
        db = get_supabase()
        result = db.table("sessions").insert({
            "user_id": user_id,
            "topic_id": topic_id,
            "session_number": session_number,
            "generated_scene_prompt": generated_scene_prompt,
            "target_vocabulary": target_vocabulary,
            "verb_focus": verb_focus,
            "message_count": 0,
            "is_completed": False
        }).execute()
        return result.data[0]["id"]
    except Exception as e:
        logger.error(f"create_session error: {e}")
        raise


def update_session_message_count(session_id: int, message_count: int):
    try:
        db = get_supabase()
        db.table("sessions").update({"message_count": message_count}).eq("id", session_id).execute()
    except Exception as e:
        logger.error(f"update_session_message_count error: {e}")


def complete_session(session_id: int):
    try:
        db = get_supabase()
        db.table("sessions").update({
            "is_completed": True,
            "ended_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", session_id).execute()
    except Exception as e:
        logger.error(f"complete_session error: {e}")


def get_completed_session_count(user_id: int, topic_id: int | None) -> int:
    """Count completed sessions for user+topic (used to compute session_number)."""
    try:
        db = get_supabase()
        query = (
            db.table("sessions")
            .select("id", count="exact")
            .eq("user_id", user_id)
            .eq("is_completed", True)
        )
        if topic_id is not None:
            query = query.eq("topic_id", topic_id)
        else:
            query = query.is_("topic_id", "null")
        result = query.execute()
        return result.count or 0
    except Exception as e:
        logger.error(f"get_completed_session_count error: {e}")
        return 0


# ── Errors ─────────────────────────────────────────────────────────────────

def save_errors(session_id: int, user_id: int, topic_id: int | None, errors: list[dict]) -> list[int]:
    """Save detected errors and return their ids."""
    if not errors:
        return []
    try:
        db = get_supabase()
        records = [
            {
                "session_id": session_id,
                "user_id": user_id,
                "topic_id": topic_id,
                "wrong_phrase": e["wrong"],
                "corrected_phrase_it": e["corrected_it"],
                "corrected_phrase_fr": e["corrected_fr"],
                "error_category": e["category"]
            }
            for e in errors
        ]
        result = db.table("errors").insert(records).execute()
        return [r["id"] for r in result.data]
    except Exception as e:
        logger.error(f"save_errors error: {e}")
        return []


def save_session_errors(
    user_id: int,
    session_id: int,
    errors: list[dict],
    topic: str | None,
    cefr_level: str | None,
):
    """Bulk-insert session errors into session_errors. Fails silently."""
    if not errors:
        return
    try:
        db = get_supabase()
        records = [
            {
                "user_id": user_id,
                "session_id": session_id,
                "wrong": e["wrong"],
                "correct": e["corrected_it"],
                "category": e["category"],
                "topic": topic,
                "cefr_level": cefr_level,
            }
            for e in errors
        ]
        db.table("session_errors").insert(records).execute()
    except Exception as e:
        logger.warning(f"save_session_errors failed (non-critical): {e}")


def save_translation_flashcard(user_id: int, original: str, phrase_fr: str, phrase_it: str) -> bool:
    """Save a /traduire result as a flashcard (no session or topic)."""
    try:
        db = get_supabase()
        result = db.table("errors").insert({
            "session_id": None,
            "user_id": user_id,
            "topic_id": None,
            "wrong_phrase": original,
            "corrected_phrase_it": phrase_it,
            "corrected_phrase_fr": phrase_fr,
            "error_category": "translation",
        }).execute()
        error_id = result.data[0]["id"]
        create_flashcards(user_id, [error_id])
        return True
    except Exception as e:
        logger.error(f"save_translation_flashcard error: {e}")
        return False


def get_user_errors(user_id: int) -> list[dict]:
    try:
        db = get_supabase()
        result = (
            db.table("errors")
            .select("*")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return result.data
    except Exception as e:
        logger.error(f"get_user_errors error: {e}")
        return []


# ── Flashcards ─────────────────────────────────────────────────────────────

def create_flashcards(user_id: int, error_ids: list[int]):
    """Create default-SM2 flashcard for each error."""
    if not error_ids:
        return
    try:
        db = get_supabase()
        records = [
            {
                "user_id": user_id,
                "error_id": error_id,
                "easiness_factor": 2.5,
                "interval_days": 1,
                "repetitions": 0,
                "next_review_at": datetime.now(timezone.utc).isoformat()
            }
            for error_id in error_ids
        ]
        db.table("flashcards").insert(records).execute()
    except Exception as e:
        logger.error(f"create_flashcards error: {e}")


def get_due_flashcards(user_id: int) -> list[dict]:
    """Return flashcards due for review, joined with error data."""
    try:
        db = get_supabase()
        now = datetime.now(timezone.utc).isoformat()
        result = (
            db.table("flashcards")
            .select("*, errors(corrected_phrase_it, corrected_phrase_fr)")
            .eq("user_id", user_id)
            .lte("next_review_at", now)
            .order("next_review_at")
            .execute()
        )
        return result.data
    except Exception as e:
        logger.error(f"get_due_flashcards error: {e}")
        return []


def update_flashcard(flashcard_id: int, easiness_factor: float, interval_days: int, repetitions: int):
    try:
        db = get_supabase()
        next_review = datetime.now(timezone.utc) + timedelta(days=interval_days)
        db.table("flashcards").update({
            "easiness_factor": easiness_factor,
            "interval_days": interval_days,
            "repetitions": repetitions,
            "next_review_at": next_review.isoformat(),
            "last_reviewed_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", flashcard_id).execute()
    except Exception as e:
        logger.error(f"update_flashcard error: {e}")
