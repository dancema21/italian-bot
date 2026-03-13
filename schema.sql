-- Whitelist of authorised users
CREATE TABLE allowed_users (
  telegram_id BIGINT PRIMARY KEY,
  added_by TEXT,
  added_at TIMESTAMPTZ DEFAULT NOW(),
  note TEXT
);

-- Registered users
CREATE TABLE users (
  id BIGSERIAL PRIMARY KEY,
  telegram_id BIGINT UNIQUE NOT NULL,
  username TEXT,
  first_name TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- CEFR topics with vocabulary list
CREATE TABLE topics (
  id BIGSERIAL PRIMARY KEY,
  cefr_level TEXT NOT NULL, -- 'A1', 'A2', 'B1', 'B2'
  title_it TEXT NOT NULL,
  title_fr TEXT NOT NULL,
  vocabulary JSONB NOT NULL -- array of Italian words/phrases
);

-- One record per user per topic to track how many times trained
CREATE TABLE user_topic_progress (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT REFERENCES users(id),
  topic_id BIGINT REFERENCES topics(id),
  session_count INT DEFAULT 0,
  last_trained_at TIMESTAMPTZ,
  UNIQUE(user_id, topic_id)
);

-- One record per conversation session
CREATE TABLE sessions (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT REFERENCES users(id),
  topic_id BIGINT REFERENCES topics(id), -- null for /verbs sessions
  session_number INT, -- nth time this user trains this topic
  generated_scene_prompt TEXT, -- the full scene the LLM generated
  target_vocabulary JSONB, -- 1-2 words the LLM was asked to push
  verb_focus TEXT, -- null for /learn sessions, tense name for /verbs sessions
  started_at TIMESTAMPTZ DEFAULT NOW(),
  ended_at TIMESTAMPTZ,
  message_count INT DEFAULT 0,
  is_completed BOOLEAN DEFAULT FALSE
);

-- Errors detected during sessions
CREATE TABLE errors (
  id BIGSERIAL PRIMARY KEY,
  session_id BIGINT REFERENCES sessions(id),
  user_id BIGINT REFERENCES users(id),
  topic_id BIGINT REFERENCES topics(id),
  wrong_phrase TEXT NOT NULL,
  corrected_phrase_it TEXT NOT NULL,
  corrected_phrase_fr TEXT NOT NULL,
  error_category TEXT NOT NULL, -- conjugation, agreement, vocabulary, prepositions, articles, spelling, word order, verb tense, pronouns, other
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Flashcards using SM-2 algorithm
CREATE TABLE flashcards (
  id BIGSERIAL PRIMARY KEY,
  user_id BIGINT REFERENCES users(id),
  error_id BIGINT REFERENCES errors(id),
  easiness_factor FLOAT DEFAULT 2.5,
  interval_days INT DEFAULT 1,
  repetitions INT DEFAULT 0,
  next_review_at TIMESTAMPTZ DEFAULT NOW(),
  last_reviewed_at TIMESTAMPTZ
);
