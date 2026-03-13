# Italian Learning Telegram Bot

A Telegram bot to learn Italian via AI-powered roleplay conversations, with spaced-repetition flashcards and error tracking. The bot interface is in **French**; conversations happen in **Italian**.

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
4. In the Railway project settings → **Variables**, add the four environment variables:
   - `TELEGRAM_BOT_TOKEN`
   - `GEMINI_API_KEY`
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
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
| `/flashcards` | Review due error flashcards (SM-2 spaced repetition) |
| `/progress` | View your session count per topic |
| `/stats` | View your error statistics |

---

## Architecture

```
bot/
├── main.py              # Entry point, message router, handler registration
├── handlers/
│   ├── start.py         # /start, /help
│   ├── learn.py         # /learn flow + active conversation
│   ├── verbs.py         # /verbs flow
│   ├── flashcards.py    # /flashcards review
│   ├── progress.py      # /progress
│   └── stats.py         # /stats
├── services/
│   ├── gemini.py        # All Gemini API calls (scene gen, chat, recap)
│   ├── supabase.py      # All database operations
│   └── sm2.py           # SM-2 spaced repetition algorithm
└── utils/
    ├── access.py        # Whitelist check helper
    └── session.py       # In-memory session state
```
