-- ClawdBot Database Schema

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Users
CREATE TABLE IF NOT EXISTS users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username    VARCHAR(64)  UNIQUE NOT NULL,
    email       VARCHAR(128) UNIQUE NOT NULL,
    password_hash TEXT        NOT NULL,
    is_active   BOOLEAN      DEFAULT TRUE,
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- Conversation memory (long-term)
CREATE TABLE IF NOT EXISTS memory_log (
    id           BIGSERIAL PRIMARY KEY,
    user_id      UUID        NOT NULL REFERENCES users(id),
    user_message TEXT        NOT NULL,
    bot_reply    TEXT        NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_memory_user ON memory_log(user_id, created_at DESC);

-- Scheduled user tasks
CREATE TABLE IF NOT EXISTS user_tasks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID        NOT NULL REFERENCES users(id),
    name            VARCHAR(128),
    prompt          TEXT        NOT NULL,
    cron_expression VARCHAR(64) NOT NULL,
    is_active       BOOLEAN     DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Notifications / task results
CREATE TABLE IF NOT EXISTS notifications (
    id         BIGSERIAL PRIMARY KEY,
    user_id    UUID        NOT NULL REFERENCES users(id),
    content    TEXT        NOT NULL,
    type       VARCHAR(64) DEFAULT 'general',
    is_read    BOOLEAN     DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_notif_user ON notifications(user_id, created_at DESC);
