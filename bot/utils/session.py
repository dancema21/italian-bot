"""In-memory session state management."""
from __future__ import annotations

active_sessions: dict = {}


def get_session(telegram_id: int) -> dict | None:
    return active_sessions.get(telegram_id)


def set_session(telegram_id: int, session: dict):
    active_sessions[telegram_id] = session


def clear_session(telegram_id: int):
    active_sessions.pop(telegram_id, None)


def update_session(telegram_id: int, **kwargs):
    if telegram_id in active_sessions:
        active_sessions[telegram_id].update(kwargs)
