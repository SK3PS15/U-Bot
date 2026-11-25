PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS owner (
    id                    INTEGER PRIMARY KEY CHECK (id = 1),
    telegram_id           INTEGER NOT NULL,
    master_password_hash  TEXT NOT NULL,
    intro_shown           INTEGER NOT NULL DEFAULT 0,
    created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS channels (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id               INTEGER NOT NULL UNIQUE,
    title                 TEXT NOT NULL,
    username              TEXT,
    chat_type             TEXT NOT NULL DEFAULT 'channel',
    is_managed            INTEGER NOT NULL DEFAULT 0,
    bot_status            TEXT,
    bot_rights_json       TEXT,
    notifications_enabled INTEGER NOT NULL DEFAULT 1,
    added_at              TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS drafts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    post_type           TEXT NOT NULL,
    text                TEXT,
    entities_json       TEXT,
    poll_json           TEXT,
    inline_buttons_json TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS draft_attachments (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id      INTEGER NOT NULL,
    position      INTEGER NOT NULL,
    file_id       TEXT NOT NULL,
    file_type     TEXT NOT NULL,
    caption       TEXT,
    metadata_json TEXT,
    FOREIGN KEY (draft_id) REFERENCES drafts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS draft_channels (
    draft_id  INTEGER NOT NULL,
    chat_id   INTEGER NOT NULL,
    PRIMARY KEY (draft_id, chat_id),
    FOREIGN KEY (draft_id) REFERENCES drafts(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS publications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    draft_id      INTEGER NOT NULL,
    scheduled_at  TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    paused        INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (draft_id) REFERENCES drafts(id)
);

CREATE TABLE IF NOT EXISTS publication_targets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id  INTEGER NOT NULL,
    chat_id         INTEGER NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    last_error      TEXT,
    message_id      INTEGER,
    sent_at         TEXT,
    UNIQUE (publication_id, chat_id),
    FOREIGN KEY (publication_id) REFERENCES publications(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS publication_prealerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    publication_id  INTEGER NOT NULL,
    minutes_before  INTEGER NOT NULL,
    sent_at         TEXT,
    FOREIGN KEY (publication_id) REFERENCES publications(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reminders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    text            TEXT NOT NULL,
    fire_at         TEXT NOT NULL,
    repeat_type     TEXT NOT NULL DEFAULT 'none',
    repeat_json     TEXT,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS notification_settings (
    key      TEXT PRIMARY KEY,
    enabled  INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS notification_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    category    TEXT NOT NULL,
    message     TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_pub_scheduled ON publications(scheduled_at, status);
CREATE INDEX IF NOT EXISTS idx_targets_pub ON publication_targets(publication_id);
CREATE INDEX IF NOT EXISTS idx_reminders_fire ON reminders(fire_at, status);
CREATE INDEX IF NOT EXISTS idx_prealerts_pub ON publication_prealerts(publication_id);
