# Italian Learning Telegram Bot

A Telegram bot to learn Italian via AI-powered roleplay conversations, with spaced-repetition flashcards and error tracking. The bot interface is in **French**; conversations happen in **Italian**.

---

## Features

### Conversation roleplay (`/learn`)
Pick a CEFR level (A1 → B2) and a topic. The bot plays a character in an immersive Italian scene — a waiter, a shopkeeper, a colleague — and steers the conversation so you naturally use the topic's vocabulary. It never interrupts to correct you; errors are silently tracked and surfaced at the end.

### Verb tense training (`/verbs`)
Choose a specific tense (Présent, Passé composé, Imparfait, Futur, Conditionnel, Subjonctif…) and the bot generates a scene designed to force you to use that tense repeatedly.

### Voice notes
Reply to the bot with a voice note instead of text. The audio is transcribed verbatim by Gemini (without correcting your Italian errors) and fed into the conversation.

### Session recap
At the end of each session — either when you type `END` or when the bot naturally closes the scene — you get:
- A structured error recap (❌ what you said → ✅ corrected Italian → 🇫🇷 French translation + error category)
- Vocabulary tips: words you overused or phrases that are grammatically correct but unnatural for native speakers

### Spaced-repetition flashcards (`/flashcards`)
Every error and vocabulary tip from your sessions is automatically turned into a flashcard using the SM-2 algorithm. Cards are shown front (French) → reveal back (Italian) → rate Correct / Incorrect. The algorithm schedules the next review based on your rating.

### Translation (`/translate`)
Enter any word or phrase in French or Italian. The bot detects the language, corrects spelling, translates it, and generates a natural example sentence in both languages. You can save the result as a flashcard in one tap.

### Progress & stats (`/progress`, `/stats`)
Track how many times you have trained each topic, and see your error statistics broken down by category (conjugation, agreement, vocabulary, prepositions, etc.).

### Admin portal
A local Streamlit app (`admin/app.py`) to manage the user whitelist, edit or delete flashcards, and browse session history and error statistics per user.

---

## Prerequisites

| What | Where to get it |
|------|----------------|
| Telegram bot token | Message [@BotFather](https://t.me/BotFather) on Telegram → `/newbot` |
| Gemini API key | [aistudio.google.com](https://aistudio.google.com) → "Get API key" |
| Supabase project URL | [supabase.com](https://supabase.com) → your project → Settings → API |
| Supabase anon key | Same page as above |

---

## Database setup

1. Go to your Supabase project → **SQL Editor**
2. Paste and run the contents of `schema.sql` to create all tables
3. Paste and run the contents of `seed.sql` to populate all CEFR topics

---

## Whitelist users

The bot is private. Only users listed in the `allowed_users` table can interact with it.

To whitelist a user, run this in the Supabase SQL Editor:

```sql
INSERT INTO allowed_users (telegram_id, added_by, note)
VALUES (123456789, 'admin', 'My name');
```

**How to find a Telegram user ID:** ask the user to message [@userinfobot](https://t.me/userinfobot) on Telegram — it will reply with their numeric user ID.

---

## Local development

1. Clone the repository
2. Copy `.env.example` to `.env` and fill in your credentials:
   ```
   TELEGRAM_BOT_TOKEN=your_token_here
   GEMINI_API_KEY=your_key_here
   SUPABASE_URL=https://xxxx.supabase.co
   SUPABASE_ANON_KEY=your_anon_key_here

   # Optional — Phoenix Cloud tracing for /ciao agent observability
   PHOENIX_API_KEY=your_key_here
   PHOENIX_COLLECTOR_ENDPOINT=https://app.phoenix.arize.com/s/your-space-name/v1/traces
   PHOENIX_PROJECT_NAME=italian-bot
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Run the bot:
   ```bash
   python -m bot.main
   ```

---

## Railway deployment

1. Push this repository to GitHub
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo**
3. Select your repository
4. In the Railway project settings → **Variables**, add the required environment variables:
   - `TELEGRAM_BOT_TOKEN`
   - `GEMINI_API_KEY`
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - *(optional)* `PHOENIX_API_KEY` — Phoenix Cloud API key for `/ciao` agent tracing
   - *(optional)* `PHOENIX_COLLECTOR_ENDPOINT` — e.g. `https://app.phoenix.arize.com/s/your-space-name/v1/traces`
   - *(optional)* `PHOENIX_PROJECT_NAME` — defaults to `italian-bot`
5. Railway will automatically detect the `Dockerfile` and deploy

The bot uses long-polling so no webhook configuration is needed.

---

## Bot commands

| Command | Description |
|---------|-------------|
| `/start` | Register and show welcome message |
| `/help` | Show available commands |
| `/learn` | Start a conversation session by CEFR level and topic |
| `/verbs` | Practice a specific verb tense |
| `/flashcards` | Review due flashcards (SM-2 spaced repetition) |
| `/translate` | Translate a word or phrase between French and Italian |
| `/progress` | View your session count per topic |
| `/stats` | View your error statistics by category |

---

## Architecture

```
bot/
├── main.py              # Entry point, message router, handler registration
├── handlers/
│   ├── start.py         # /start, /help
│   ├── learn.py         # /learn flow + active conversation + recap
│   ├── verbs.py         # /verbs flow
│   ├── flashcards.py    # /flashcards review
│   ├── translate.py     # /translate command
│   ├── progress.py      # /progress
│   └── stats.py         # /stats
├── services/
│   ├── gemini.py        # All Gemini API calls (scene gen, chat, recap, translation)
│   ├── supabase.py      # All database operations
│   └── sm2.py           # SM-2 spaced repetition algorithm
└── utils/
    ├── access.py        # Whitelist check helper
    └── session.py       # In-memory session state
```
