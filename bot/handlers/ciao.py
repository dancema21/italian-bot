"""Handler for /ciao — agentic personalized session launcher."""
from __future__ import annotations
import logging
import random

from telegram import Update
from telegram.ext import ContextTypes
from google.genai import types

from bot.utils.access import check_access
from bot.utils.session import set_session
from bot.services import supabase as db
from bot.services.gemini import get_client, MODEL, generate_scene as gemini_generate_scene, build_learn_system_prompt
from bot.services.agent_tools import (
    get_recent_errors,
    get_flashcard_performance,
    get_session_history,
    get_topic_list,
)

logger = logging.getLogger(__name__)

MAX_ITERATIONS = 6

_SYSTEM_PROMPT = (
    "You are a personalized Italian tutor. Your goal is to design the best possible "
    "learning session for this user based on their history.\n\n"
    "You have access to tools. Use them to understand the user's weak points, "
    "recent topics, and flashcard failures. Then call generate_scene with a level, "
    "topic, and specific constraints targeting their weaknesses.\n\n"
    "Be efficient: 2-4 tool calls maximum before calling generate_scene. "
    "Reason step by step before each tool call."
)

_AGENT_TOOLS = types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name="get_recent_errors",
        description="Get the last 20 errors the user made across all sessions. Returns wrong phrase, correct phrase, category, and topic.",
        parameters=types.Schema(type="OBJECT", properties={}),
    ),
    types.FunctionDeclaration(
        name="get_flashcard_performance",
        description="Get flashcards with poor performance (low easiness factor) indicating the user's weakest areas.",
        parameters=types.Schema(type="OBJECT", properties={}),
    ),
    types.FunctionDeclaration(
        name="get_session_history",
        description="Get the user's completed sessions grouped by topic with count and last trained date.",
        parameters=types.Schema(type="OBJECT", properties={}),
    ),
    types.FunctionDeclaration(
        name="get_topic_list",
        description="Get the full list of available learning topics with their CEFR levels.",
        parameters=types.Schema(type="OBJECT", properties={}),
    ),
    types.FunctionDeclaration(
        name="generate_scene",
        description=(
            "Terminal tool. Call this once you have decided on the best topic and level for the user. "
            "This ends the agent loop and launches the learning session."
        ),
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "level": types.Schema(
                    type="STRING",
                    description="CEFR level: A1, A2, B1, or B2",
                ),
                "topic": types.Schema(
                    type="STRING",
                    description="Italian topic title exactly as returned by get_topic_list",
                ),
                "constraints": types.Schema(
                    type="STRING",
                    description=(
                        "Plain text describing what to focus on in the scene, "
                        "targeting the user's weaknesses (e.g. 'force use of prepositions a/in/da, "
                        "avoid passato prossimo')"
                    ),
                ),
            },
            required=["level", "topic", "constraints"],
        ),
    ),
])


def _collect_function_calls(parts) -> list:
    calls = []
    for part in parts:
        try:
            if part.function_call and part.function_call.name:
                calls.append(part.function_call)
        except Exception:
            pass
    return calls


def _execute_tool(name: str, user_id: int) -> list | dict:
    if name == "get_recent_errors":
        return get_recent_errors(user_id)
    if name == "get_flashcard_performance":
        return get_flashcard_performance(user_id)
    if name == "get_session_history":
        return get_session_history(user_id)
    if name == "get_topic_list":
        return get_topic_list()
    return {}


async def _run_agent_loop(user_id: int) -> dict | None:
    """
    ReAct loop: LLM calls tools until it calls generate_scene (terminal).
    Returns the generate_scene args dict, or None if capped / errored.
    """
    client = get_client()
    contents = [
        types.Content(
            role="user",
            parts=[types.Part(text="Analyse my learning data and design the best session for me.")],
        )
    ]

    for _ in range(MAX_ITERATIONS):
        try:
            response = await client.aio.models.generate_content(
                model=MODEL,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=_SYSTEM_PROMPT,
                    tools=[_AGENT_TOOLS],
                    temperature=0.3,
                ),
            )
        except Exception as e:
            logger.error(f"Agent LLM call failed: {e}")
            return None

        model_parts = response.candidates[0].content.parts
        contents.append(types.Content(role="model", parts=model_parts))

        fn_calls = _collect_function_calls(model_parts)
        if not fn_calls:
            # No tool calls — unexpected, exit loop
            break

        fn_responses = []
        terminal = None

        for fc in fn_calls:
            if fc.name == "generate_scene":
                terminal = dict(fc.args)
                break
            result = _execute_tool(fc.name, user_id)
            fn_responses.append(
                types.Part.from_function_response(
                    name=fc.name,
                    response={"result": result},
                )
            )

        if terminal:
            return terminal

        if fn_responses:
            contents.append(types.Content(role="user", parts=fn_responses))

    return None


def _fallback_topic(user_id: int) -> tuple[dict | None, str]:
    """Return (topic_db_row, cefr_level) when agent loop fails."""
    history = get_session_history(user_id)
    level = history[0]["cefr_level"] if history else "A1"
    topics = db.get_topics_by_level(level)
    if not topics:
        return None, level
    return random.choice(topics), level


async def ciao_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await check_access(update, context):
        return

    telegram_id = update.effective_user.id
    user_id = db.upsert_user(
        telegram_id,
        update.effective_user.username,
        update.effective_user.first_name,
    )

    await update.message.reply_text("⏳ Je prépare ta session...")

    agent_result = await _run_agent_loop(user_id)

    if agent_result:
        level = agent_result.get("level", "A1")
        topic_title = agent_result.get("topic", "")
        constraints = agent_result.get("constraints", "")

        topics = db.get_topics_by_level(level)
        topic = next(
            (t for t in topics if t["title_it"].lower() == topic_title.lower()),
            None,
        )
        if not topic and topics:
            topic = random.choice(topics)
    else:
        topic, level = _fallback_topic(user_id)
        constraints = ""

    if not topic:
        await update.message.reply_text(
            "Impossible de préparer une session. Utilise /learn pour choisir manuellement."
        )
        return

    await _launch_scene(update, context, telegram_id, user_id, topic, constraints)


async def _launch_scene(update, context, telegram_id, user_id, topic, constraints):
    """Generate scene and start session — mirrors learn_topic_callback exactly."""
    cefr_level = topic["cefr_level"]

    try:
        scene = await gemini_generate_scene(
            cefr_level=cefr_level,
            topic_title_it=topic["title_it"],
            vocabulary_sample=topic["vocabulary"],
        )
    except Exception as e:
        logger.error(f"Scene generation failed: {e}")
        await update.message.reply_text("Erreur lors de la génération de la scène. Réessaie.")
        return

    max_messages = random.randint(10, 15)
    session_number = db.get_completed_session_count(user_id, topic["id"]) + 1

    try:
        session_db_id = db.create_session(
            user_id=user_id,
            topic_id=topic["id"],
            session_number=session_number,
            generated_scene_prompt=scene["scene_prompt"],
            target_vocabulary=scene["target_vocabulary"],
            verb_focus=None,
        )
    except Exception as e:
        logger.error(f"Session creation failed: {e}")
        await update.message.reply_text("Erreur lors de la création de la session. Réessaie.")
        return

    system_prompt = build_learn_system_prompt(
        cefr_level=cefr_level,
        topic_title_it=topic["title_it"],
        generated_scene_prompt=scene["scene_prompt"],
        target_vocabulary=scene["target_vocabulary"],
        max_messages=max_messages,
    )
    if constraints:
        system_prompt += f"\n\nADDITIONAL FOCUS FOR THIS SESSION:\n{constraints}"

    opening = scene["opening_line_it"]
    initial_history = [
        {"role": "user", "parts": ["[inizia la scena]"]},
        {"role": "model", "parts": [opening]},
    ]

    set_session(telegram_id, {
        "session_db_id": session_db_id,
        "topic_id": topic["id"],
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

    await update.message.reply_text(
        f"🇮🇹 *{topic['title_fr']}* — Niveau {cefr_level}\n\n"
        f"_(Envoie *END* à tout moment pour terminer la session et voir le récap)_",
        parse_mode="Markdown",
    )
    await context.bot.send_message(chat_id=update.effective_chat.id, text=opening)
