"""All Gemini API calls using the google-genai SDK."""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    return _client


async def transcribe_voice(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """
    Transcribe a voice note verbatim — no error correction.
    Returns the raw transcription exactly as spoken.
    """
    prompt = (
        "Transcribe this Italian audio exactly as spoken, word for word.\n"
        "Do NOT correct any grammar, conjugation, vocabulary, or word order errors.\n"
        "Do NOT improve, rephrase, or complete anything.\n"
        "Output only the raw transcription, nothing else."
    )
    try:
        client = get_client()
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                types.Part(text=prompt),
            ],
            config=types.GenerateContentConfig(temperature=0.0),
        )
        return response.text.strip()
    except Exception as e:
        logger.error(f"transcribe_voice error: {e}")
        raise


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


async def generate_scene(
    cefr_level: str,
    topic_title_it: str,
    vocabulary_sample: list,
    verb_focus: str | None = None,
) -> dict:
    """Generate scene JSON. Returns dict with scene_prompt, target_vocabulary, opening_line_it."""
    vocab_str = ", ".join(vocabulary_sample[:8])

    if verb_focus:
        extra = (
            f"\nMode: verb tense training. Target tense: {verb_focus}\n"
            f"Create a scene that forces natural and repeated use of {verb_focus}."
        )
    else:
        extra = ""

    prompt = (
        f"Generate a short roleplay scene to practice Italian.\n"
        f"Level: {cefr_level}\n"
        f"Topic: {topic_title_it}\n"
        f"Key vocabulary to integrate: {vocab_str}{extra}\n\n"
        'Reply ONLY with this JSON, no markdown, no backticks, raw JSON only:\n'
        '{\n'
        '  "scene_prompt": "Short description of the role you will play (2-3 sentences max)",\n'
        '  "target_vocabulary": ["word1", "word2"],\n'
        '  "opening_line_it": "A single Italian sentence that both sets the scene and naturally opens the conversation, as if you are already in character"\n'
        '}'
    )

    try:
        client = get_client()
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.9),
        )
        raw = _strip_code_fences(response.text)
        return json.loads(raw)
    except Exception as e:
        logger.error(f"generate_scene error: {e}")
        raise


def build_learn_system_prompt(
    cefr_level: str,
    topic_title_it: str,
    generated_scene_prompt: str,
    target_vocabulary: list,
    max_messages: int,
) -> str:
    vocab_str = ", ".join(target_vocabulary)
    return (
        "You are an expert Italian teacher playing a role in a conversation scene.\n"
        "Conversation language: Italian only.\n"
        f"User's CEFR level: {cefr_level}\n"
        f"Topic: {topic_title_it}\n"
        f"Scene: {generated_scene_prompt}\n\n"
        "Absolute rules:\n"
        "1. Stay in character in Italian ONLY. Never switch to French or English during the conversation.\n"
        "2. NEVER interrupt the conversation to correct errors. Note them silently.\n"
        f"3. Naturally steer the conversation so the user is pushed to use these vocabulary words: {vocab_str}. Create situations where these words become necessary.\n"
        f"4. The conversation lasts {max_messages} exchanges. As you approach the last 2 messages, close the scene NATURALLY in Italian as if you suddenly have to leave "
        "(e.g. \"Ho un appuntamento, devo andare — arrivederci!\"). Never mention that the session is ending.\n"
        '5. After each message, on a new hidden line, log any errors detected in THAT message using this exact format: <!--ERRORS:[{"wrong":"...","corrected_it":"...","corrected_fr":"...","category":"..."}]-->\n'
        "   If no errors: <!--ERRORS:[]-->\n"
        "   The corrected_fr field must always be the French translation of the corrected Italian phrase.\n\n"
        "Allowed error categories: conjugation, agreement, vocabulary, prepositions, articles, spelling, word order, verb tense, pronouns, other"
    )


def build_verbs_system_prompt(
    cefr_level: str,
    verb_focus: str,
    generated_scene_prompt: str,
    target_vocabulary: list,
    max_messages: int,
) -> str:
    vocab_str = ", ".join(target_vocabulary)
    return (
        "You are an expert Italian teacher playing a role in a conversation scene.\n"
        "Conversation language: Italian only.\n"
        f"User's CEFR level: {cefr_level}\n"
        "Mode: verb tense training.\n"
        f"Target tense: {verb_focus}\n"
        f"Scene: {generated_scene_prompt}\n"
        f"Create a conversation scene that FORCES the user to use {verb_focus} naturally and repeatedly. "
        f"If the user avoids the target tense, steer the conversation to make it necessary. "
        f"Errors on {verb_focus} are the highest priority to log.\n\n"
        "Absolute rules:\n"
        "1. Stay in character in Italian ONLY. Never switch to French or English during the conversation.\n"
        "2. NEVER interrupt the conversation to correct errors. Note them silently.\n"
        f"3. Naturally steer the conversation so the user is pushed to use these vocabulary words: {vocab_str}. Create situations where these words become necessary.\n"
        f"4. The conversation lasts {max_messages} exchanges. As you approach the last 2 messages, close the scene NATURALLY in Italian as if you suddenly have to leave "
        "(e.g. \"Ho un appuntamento, devo andare — arrivederci!\"). Never mention that the session is ending.\n"
        '5. After each message, on a new hidden line, log any errors detected in THAT message using this exact format: <!--ERRORS:[{"wrong":"...","corrected_it":"...","corrected_fr":"...","category":"..."}]-->\n'
        "   If no errors: <!--ERRORS:[]-->\n"
        "   The corrected_fr field must always be the French translation of the corrected Italian phrase.\n\n"
        "Allowed error categories: conjugation, agreement, vocabulary, prepositions, articles, spelling, word order, verb tense, pronouns, other"
    )


async def send_message(
    system_prompt: str,
    conversation_history: list[dict],
    user_message: str,
    closing_hint: bool = False,
) -> str:
    """Send a user message within an ongoing conversation and return the model reply."""
    if closing_hint:
        system_prompt = (
            system_prompt
            + "\n\n[IMPORTANT: Begin naturally closing the scene in your next response, "
            "as if you suddenly have to leave. Do it in Italian, completely in character.]"
        )

    contents = []
    for turn in conversation_history:
        contents.append(types.Content(
            role=turn["role"],
            parts=[types.Part(text=p) for p in turn["parts"]],
        ))
    contents.append(types.Content(
        role="user",
        parts=[types.Part(text=user_message)],
    ))

    try:
        client = get_client()
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.9,
            ),
        )
        return response.text
    except Exception as e:
        logger.error(f"send_message error: {e}")
        raise


async def generate_recap(
    errors: list[dict],
    target_vocabulary: list,
    vocabulary_used: list,
    user_messages: list[str] | None = None,
) -> str:
    """Generate session recap in French — errors + vocabulary tips."""
    errors_section = ""
    if errors:
        errors_json = json.dumps(errors, ensure_ascii=False, indent=2)
        errors_section = (
            f"DETECTED ERRORS:\n{errors_json}\n\n"
            "List EVERY error using EXACTLY this format, one block per error:\n"
            "❌ [wrong phrase]\n"
            "✅ [corrected Italian]\n"
            "🇫🇷 [French translation]\n"
            "📌 Catégorie : [category in French — mapping: conjugation→Conjugaison, "
            "agreement→Accord, vocabulary→Vocabulaire, prepositions→Prépositions, articles→Articles, "
            "spelling→Orthographe, word order→Ordre des mots, verb tense→Temps verbaux, "
            "pronouns→Pronoms, other→Autre]\n\n"
            "Include ALL errors. No introduction, no summary between errors.\n\n"
        )
    else:
        errors_section = "No errors were detected in this session.\n\n"

    messages_block = ""
    if user_messages:
        joined = "\n".join(f"- {m}" for m in user_messages)
        messages_block = f"USER'S MESSAGES DURING THE SESSION:\n{joined}\n\n"

    prompt = (
        f"{errors_section}"
        f"{messages_block}"
        "Now write a section titled '💡 Conseils de vocabulaire' IN FRENCH.\n"
        "Analyse the user's messages and identify:\n"
        "1. Words or expressions used too repetitively — suggest varied Italian alternatives.\n"
        "2. Phrases that are grammatically correct but unnatural or rarely used by native Italian speakers — explain the more natural version.\n"
        "Format rules (strictly follow):\n"
        "- No subtitles, no section names, no bold markers (**), no markdown formatting of any kind.\n"
        "- Each tip as a plain bullet point starting with •\n"
        "- Be specific and cite the actual words/phrases the user used.\n"
        "- If nothing notable: write '💡 Conseils de vocabulaire\n\nRien à signaler.'\n"
        "- Do not repeat errors already listed above.\n\n"
        "After the vocabulary section, on a HIDDEN final line output structured flashcard data using this EXACT format:\n"
        '<!--VOCAB_TIPS:[{"original":"phrase the user wrote","phrase_it":"better Italian phrase","phrase_fr":"description en français pour la flashcard"}]-->\n'
        "Include only tips genuinely worth memorising as flashcards (0 to 3 items). "
        "Each phrase_fr should be a concise French label suitable as a flashcard front (e.g. 'Je voudrais (forme polie)'). "
        "If no tips worth creating: <!--VOCAB_TIPS:[]-->"
    )

    try:
        client = get_client()
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.7),
        )
        return response.text
    except Exception as e:
        logger.error(f"generate_recap error: {e}")
        raise


def extract_errors(text: str) -> tuple[str, list[dict]]:
    """Parse and strip <!--ERRORS:[...]--> tags from LLM response."""
    pattern = r'<!--ERRORS:(.*?)-->'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        try:
            errors = json.loads(match.group(1))
        except json.JSONDecodeError:
            errors = []
        clean_text = re.sub(pattern, '', text).strip()
        return clean_text, errors
    return text, []


def extract_vocab_tips(text: str) -> tuple[str, list[dict]]:
    """Parse and strip <!--VOCAB_TIPS:[...]--> tag from recap text."""
    pattern = r'<!--VOCAB_TIPS:(.*?)-->'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        try:
            tips = json.loads(match.group(1))
        except json.JSONDecodeError:
            tips = []
        clean_text = re.sub(pattern, '', text).strip()
        return clean_text, tips
    return text, []


async def search_italian_news() -> list[dict]:
    """Search for recent Italian news articles using Tavily, then summarise with Gemini."""
    from tavily import AsyncTavilyClient

    logger.info("search_italian_news: searching via Tavily")
    tavily = AsyncTavilyClient(api_key=os.environ["TAVILY_API_KEY"])

    try:
        results = await tavily.search(
            query="notizie Italia oggi attualità",
            search_depth="basic",
            max_results=8,
            include_domains=[
                "corriere.it", "repubblica.it", "lastampa.it",
                "ansa.it", "rainews.it", "ilsole24ore.com", "ilmessaggero.it",
            ],
        )
    except Exception as e:
        logger.error(f"Tavily search error: {e}", exc_info=True)
        raise

    hits = results.get("results", [])
    logger.info(f"search_italian_news: Tavily returned {len(hits)} results")
    if not hits:
        raise ValueError("Tavily returned no results")

    # Build a compact context block for Gemini to summarise
    snippets = []
    for h in hits[:8]:
        snippets.append(
            f"TITLE: {h.get('title', '')}\n"
            f"URL: {h.get('url', '')}\n"
            f"SNIPPET: {h.get('content', '')[:300]}"
        )
    context = "\n\n---\n\n".join(snippets)

    prompt = (
        "Below are recent Italian news articles found via web search.\n"
        "Select the 5 most interesting and diverse articles.\n"
        "For each, write a 2-sentence summary IN FRENCH.\n\n"
        f"{context}\n\n"
        "Reply ONLY with a JSON array, no markdown, no backticks:\n"
        '[\n'
        '  {"title": "article title", "source": "domain name (e.g. corriere.it)", '
        '"url": "https://full-url", "summary_fr": "résumé en 2 phrases en français"}\n'
        ']\n'
        "Return exactly 5 objects."
    )

    try:
        client = get_client()
        logger.info("search_italian_news: calling Gemini to summarise")
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.2),
        )
        raw = _strip_code_fences(response.text)
        match = re.search(r'\[.*\]', raw, re.DOTALL)
        if not match:
            logger.error(f"search_italian_news: no JSON array in Gemini response: {raw[:300]}")
            raise ValueError("No JSON array in Gemini response")
        articles = json.loads(match.group(0))[:5]
        logger.info(f"search_italian_news: {len(articles)} articles ready")
        return articles
    except Exception as e:
        logger.error(f"search_italian_news Gemini summarise error: {type(e).__name__}: {e}", exc_info=True)
        raise



def _build_notizie_system_prompt(article: dict, message_count: int) -> str:
    if message_count < 3:
        focus = (
            "Phase compréhension : pose 1 ou 2 questions ouvertes en italien pour vérifier "
            "que l'utilisateur a bien compris l'article. Demande-lui de résumer les faits, "
            "d'identifier les acteurs impliqués ou d'expliquer les événements principaux. "
            "Ne donne pas les réponses toi-même — laisse l'utilisateur s'exprimer."
        )
    else:
        focus = (
            "Phase analyse : engage une discussion plus profonde en italien. "
            "Explore les implications de l'événement, le contexte historique ou politique, "
            "des situations similaires dans d'autres pays ou dans le passé, "
            "et ce qui pourrait se passer ensuite. Partage ton point de vue et invite l'utilisateur à réagir."
        )
    return (
        "Tu discutes d'un article d'actualité avec un apprenant de l'italien.\n"
        f"Article : \"{article['title']}\" ({article['source']})\n\n"
        "Règles absolues :\n"
        "1. Réponds TOUJOURS en italien, même si l'utilisateur écrit en français.\n"
        "2. Sois concis : 3 à 5 phrases par réponse maximum.\n"
        "3. Si l'utilisateur fait une erreur d'italien notable, signale-la brièvement "
        "à la fin de ta réponse entre parenthèses : (NB: si dice '...' non '...')\n"
        f"4. {focus}"
    )


async def notizie_chat(
    article: dict,
    conversation_history: list[dict],
    user_message: str,
    message_count: int,
) -> str:
    """Handle one turn of a news article discussion in Italian."""
    system_prompt = _build_notizie_system_prompt(article, message_count)

    contents = []
    for turn in conversation_history:
        contents.append(types.Content(
            role=turn["role"],
            parts=[types.Part(text=p) for p in turn["parts"]],
        ))
    contents.append(types.Content(
        role="user",
        parts=[types.Part(text=user_message)],
    ))

    try:
        client = get_client()
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.7,
            ),
        )
        return response.text
    except Exception as e:
        logger.error(f"notizie_chat error: {e}")
        raise


async def translate_word(text: str) -> dict:
    """Detect language (FR/IT), correct spelling, translate, return example sentences."""
    prompt = (
        f'The user entered: "{text}"\n\n'
        "1. Detect whether this is French or Italian (ignore spelling mistakes).\n"
        "2. Correct any spelling mistakes in the input.\n"
        "3. Write one short, natural example sentence that includes the corrected word/phrase (source language). "
        "The word may appear in its conjugated form if it is a verb, or in plural if it is a noun — use whatever form fits naturally in the sentence.\n"
        "4. Translate both the corrected word/phrase and the example sentence into the other language.\n\n"
        "Reply ONLY with this JSON, no markdown, no backticks, raw JSON only:\n"
        "{\n"
        '  "source_lang": "fr",\n'
        '  "source_word": "corrected word/phrase in source language",\n'
        '  "source_sentence": "example sentence in source language",\n'
        '  "target_word": "translation in target language",\n'
        '  "target_sentence": "translated example sentence in target language"\n'
        "}\n"
        'source_lang must be "fr" if the input is French, "it" if Italian.'
    )
    try:
        client = get_client()
        response = await client.aio.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(temperature=0.3),
        )
        raw = _strip_code_fences(response.text)
        return json.loads(raw)
    except Exception as e:
        logger.error(f"translate_word error: {e}")
        raise


def detect_vocabulary_usage(text: str, target_vocabulary: list) -> list[str]:
    """Return which target vocabulary words appear in the user's text (case-insensitive)."""
    text_lower = text.lower()
    return [word for word in target_vocabulary if word.lower() in text_lower]
