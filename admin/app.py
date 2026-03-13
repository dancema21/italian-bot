"""Italian Bot — Admin Interface (Streamlit)."""
import os
import sys

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from supabase import create_client, Client

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Italian Bot — Admin",
    page_icon="🇮🇹",
    layout="wide",
)

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
CATEGORIES = list(CATEGORY_FR.keys())


# ── Auth ────────────────────────────────────────────────────────────────────
def check_auth():
    if st.session_state.get("authenticated"):
        return True
    st.title("🇮🇹 Italian Bot — Admin")
    pwd = st.text_input("Mot de passe", type="password")
    if st.button("Se connecter"):
        if pwd == os.environ.get("ADMIN_PASSWORD", ""):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Mot de passe incorrect.")
    return False


# ── Supabase ────────────────────────────────────────────────────────────────
@st.cache_resource
def get_db() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_ANON_KEY"])


# ── Helpers ─────────────────────────────────────────────────────────────────
def load_users():
    db = get_db()
    res = db.table("users").select("id, telegram_id, username, first_name, created_at").order("created_at", desc=True).execute()
    return res.data or []


def user_label(u: dict) -> str:
    name = u.get("first_name") or u.get("username") or "?"
    return f"{name} (id: {u['telegram_id']})"


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1 — Allowed Users
# ══════════════════════════════════════════════════════════════════════════════
def page_allowed_users():
    st.header("👥 Utilisateurs autorisés")
    db = get_db()

    # Load current whitelist
    rows = db.table("allowed_users").select("*").order("added_at", desc=True).execute().data or []

    if rows:
        df = pd.DataFrame(rows)[["telegram_id", "added_by", "note", "added_at"]]
        df.columns = ["Telegram ID", "Ajouté par", "Note", "Date d'ajout"]
        st.dataframe(df, use_container_width=True, hide_index=True)
    else:
        st.info("Aucun utilisateur autorisé.")

    st.divider()

    # Add user
    st.subheader("Ajouter un utilisateur")
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        new_id = st.number_input("Telegram ID", min_value=1, step=1, format="%d")
    with col2:
        new_note = st.text_input("Note (optionnel)")
    with col3:
        st.write("")
        st.write("")
        if st.button("Ajouter", use_container_width=True):
            try:
                db.table("allowed_users").insert({
                    "telegram_id": int(new_id),
                    "added_by": "admin",
                    "note": new_note or None,
                }).execute()
                st.success(f"Utilisateur {new_id} ajouté.")
                st.rerun()
            except Exception as e:
                st.error(f"Erreur : {e}")

    st.divider()

    # Remove user
    if rows:
        st.subheader("Supprimer un utilisateur")
        ids = [str(r["telegram_id"]) for r in rows]
        to_remove = st.selectbox("Sélectionner", ids)
        if st.button("Supprimer", type="primary"):
            db.table("allowed_users").delete().eq("telegram_id", int(to_remove)).execute()
            st.success(f"Utilisateur {to_remove} supprimé.")
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2 — Flashcards
# ══════════════════════════════════════════════════════════════════════════════
def page_flashcards():
    st.header("🃏 Flashcards")
    db = get_db()
    users = load_users()

    if not users:
        st.info("Aucun utilisateur enregistré.")
        return

    selected = st.selectbox("Utilisateur", users, format_func=user_label)
    user_id = selected["id"]

    # Load flashcards joined with errors
    res = db.table("flashcards").select(
        "id, easiness_factor, interval_days, repetitions, next_review_at, last_reviewed_at, "
        "errors(id, wrong_phrase, corrected_phrase_it, corrected_phrase_fr, error_category)"
    ).eq("user_id", user_id).order("next_review_at").execute()
    cards = res.data or []

    if not cards:
        st.info("Aucune flashcard pour cet utilisateur.")
        return

    st.caption(f"{len(cards)} flashcard(s)")

    for card in cards:
        err = card.get("errors") or {}
        cat_fr = CATEGORY_FR.get(err.get("error_category", ""), err.get("error_category", ""))
        with st.expander(f"🇫🇷 {err.get('corrected_phrase_fr', '?')}  —  📌 {cat_fr}"):
            col1, col2 = st.columns(2)

            with col1:
                new_fr = st.text_input("Français", value=err.get("corrected_phrase_fr", ""), key=f"fr_{card['id']}")
                new_it = st.text_input("Italien", value=err.get("corrected_phrase_it", ""), key=f"it_{card['id']}")
                new_cat = st.selectbox(
                    "Catégorie",
                    CATEGORIES,
                    index=CATEGORIES.index(err.get("error_category", "other")) if err.get("error_category") in CATEGORIES else 0,
                    format_func=lambda c: CATEGORY_FR[c],
                    key=f"cat_{card['id']}"
                )

            with col2:
                st.caption(f"Répétitions : {card['repetitions']}")
                st.caption(f"Intervalle : {card['interval_days']} jour(s)")
                st.caption(f"Facteur de facilité : {card['easiness_factor']:.2f}")
                st.caption(f"Prochaine révision : {(card['next_review_at'] or '')[:10]}")

            bcol1, bcol2 = st.columns(2)
            with bcol1:
                if st.button("💾 Enregistrer", key=f"save_{card['id']}", use_container_width=True):
                    try:
                        db.table("errors").update({
                            "corrected_phrase_fr": new_fr,
                            "corrected_phrase_it": new_it,
                            "error_category": new_cat,
                        }).eq("id", err["id"]).execute()
                        st.success("Enregistré.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur : {e}")
            with bcol2:
                if st.button("🗑 Supprimer", key=f"del_{card['id']}", use_container_width=True, type="primary"):
                    try:
                        db.table("flashcards").delete().eq("id", card["id"]).execute()
                        st.success("Flashcard supprimée.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Erreur : {e}")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3 — Progress
# ══════════════════════════════════════════════════════════════════════════════
def page_progress():
    st.header("📊 Progression")
    db = get_db()
    users = load_users()

    if not users:
        st.info("Aucun utilisateur enregistré.")
        return

    selected = st.selectbox("Utilisateur", users, format_func=user_label)
    user_id = selected["id"]

    # ── Topic progress ───────────────────────────────────────────────────────
    st.subheader("Thèmes")
    topics_res = db.table("topics").select("id, cefr_level, title_fr").order("cefr_level").order("id").execute()
    topics = {t["id"]: t for t in (topics_res.data or [])}

    prog_res = db.table("user_topic_progress").select("topic_id, session_count, last_trained_at").eq("user_id", user_id).execute()
    prog_map = {p["topic_id"]: p for p in (prog_res.data or [])}

    levels = ["A1", "A2", "B1", "B2"]
    for level in levels:
        level_topics = [t for t in topics.values() if t["cefr_level"] == level]
        if not level_topics:
            continue
        rows = []
        for t in level_topics:
            p = prog_map.get(t["id"], {})
            rows.append({
                "Thème": t["title_fr"],
                "Sessions": p.get("session_count", 0),
                "Dernière session": (p.get("last_trained_at") or "—")[:10],
            })
        df = pd.DataFrame(rows)
        st.markdown(f"**{level}**")
        st.dataframe(df, use_container_width=True, hide_index=True)

    # ── Sessions history ─────────────────────────────────────────────────────
    st.subheader("Historique des sessions")
    sess_res = db.table("sessions").select(
        "id, started_at, ended_at, message_count, is_completed, verb_focus, topic_id"
    ).eq("user_id", user_id).order("started_at", desc=True).limit(20).execute()
    sessions = sess_res.data or []

    if sessions:
        rows = []
        for s in sessions:
            topic = topics.get(s["topic_id"], {})
            rows.append({
                "Date": (s["started_at"] or "")[:10],
                "Thème": topic.get("title_fr") or (f"Verbes — {s['verb_focus']}" if s["verb_focus"] else "—"),
                "Messages": s["message_count"],
                "Terminée": "✅" if s["is_completed"] else "⏳",
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("Aucune session.")

    # ── Error stats ──────────────────────────────────────────────────────────
    st.subheader("Statistiques d'erreurs")
    err_res = db.table("errors").select("error_category, wrong_phrase, corrected_phrase_it").eq("user_id", user_id).execute()
    errors = err_res.data or []

    if not errors:
        st.info("Aucune erreur enregistrée.")
        return

    st.metric("Total d'erreurs", len(errors))

    # By category
    cat_counts = {}
    for e in errors:
        c = e["error_category"]
        cat_counts[c] = cat_counts.get(c, 0) + 1
    cat_df = pd.DataFrame([
        {"Catégorie": CATEGORY_FR.get(c, c), "Erreurs": n}
        for c, n in sorted(cat_counts.items(), key=lambda x: -x[1])
    ])
    st.dataframe(cat_df, use_container_width=True, hide_index=True)

    # Top wrong phrases
    st.subheader("Erreurs les plus fréquentes")
    phrase_counts = {}
    phrase_correction = {}
    for e in errors:
        p = e["wrong_phrase"]
        phrase_counts[p] = phrase_counts.get(p, 0) + 1
        phrase_correction[p] = e["corrected_phrase_it"]
    top = sorted(phrase_counts.items(), key=lambda x: -x[1])[:10]
    top_df = pd.DataFrame([
        {"Erreur": p, "Correction": phrase_correction[p], "Occurrences": n}
        for p, n in top
    ])
    st.dataframe(top_df, use_container_width=True, hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════
def main():
    if not check_auth():
        return

    st.sidebar.title("🇮🇹 Italian Bot")
    st.sidebar.markdown("---")
    page = st.sidebar.radio(
        "Navigation",
        ["👥 Utilisateurs autorisés", "🃏 Flashcards", "📊 Progression"],
    )
    st.sidebar.markdown("---")
    if st.sidebar.button("Se déconnecter"):
        st.session_state["authenticated"] = False
        st.rerun()

    if page == "👥 Utilisateurs autorisés":
        page_allowed_users()
    elif page == "🃏 Flashcards":
        page_flashcards()
    elif page == "📊 Progression":
        page_progress()


if __name__ == "__main__":
    main()
