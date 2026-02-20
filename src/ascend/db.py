"""SQLite database layer for Ascend."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = 2

_SCHEMA_SQL = """\
-- Schema version tracking
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Teams (hierarchical)
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    parent_id INTEGER REFERENCES teams(id),
    lead_id INTEGER REFERENCES members(id),
    description TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Members
CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    personal_email TEXT,
    github TEXT UNIQUE,
    slack TEXT,
    phone TEXT,
    title TEXT,
    team_id INTEGER REFERENCES teams(id),
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Member flags (user-defined searchable tags)
CREATE TABLE IF NOT EXISTS member_flags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    flag TEXT NOT NULL,
    set_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(member_id, flag)
);

-- Team-member many-to-many
CREATE TABLE IF NOT EXISTS team_members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    member_id INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member',
    joined_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(team_id, member_id)
);

-- Meetings / 1:1s
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL REFERENCES members(id),
    date TEXT NOT NULL,
    source TEXT,
    source_file TEXT,
    raw_text TEXT,
    summary TEXT,
    sentiment_score REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- FTS5 for transcript search
CREATE VIRTUAL TABLE IF NOT EXISTS meetings_fts USING fts5(
    raw_text,
    summary,
    content=meetings,
    content_rowid=id
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS meetings_ai AFTER INSERT ON meetings BEGIN
    INSERT INTO meetings_fts(rowid, raw_text, summary)
    VALUES (new.id, new.raw_text, new.summary);
END;

CREATE TRIGGER IF NOT EXISTS meetings_ad AFTER DELETE ON meetings BEGIN
    INSERT INTO meetings_fts(meetings_fts, rowid, raw_text, summary)
    VALUES ('delete', old.id, old.raw_text, old.summary);
END;

CREATE TRIGGER IF NOT EXISTS meetings_au AFTER UPDATE ON meetings BEGIN
    INSERT INTO meetings_fts(meetings_fts, rowid, raw_text, summary)
    VALUES ('delete', old.id, old.raw_text, old.summary);
    INSERT INTO meetings_fts(rowid, raw_text, summary)
    VALUES (new.id, new.raw_text, new.summary);
END;

-- Meeting items (extracted from meetings)
CREATE TABLE IF NOT EXISTS meeting_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,  -- action_item, decision, topic, concern, win
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Goals (OKRs, PIP criteria, career milestones)
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER REFERENCES members(id),
    team_id INTEGER REFERENCES teams(id),
    cycle TEXT,
    type TEXT NOT NULL,  -- objective, key_result, pip_criterion, career_milestone
    title TEXT NOT NULL,
    description TEXT,
    target_value REAL,
    current_value REAL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Performance snapshots (time-series)
CREATE TABLE IF NOT EXISTS performance_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL REFERENCES members(id),
    date TEXT NOT NULL,
    source TEXT NOT NULL,  -- github, linear, manual
    metrics TEXT NOT NULL,  -- JSON blob
    score REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Coaching entries
CREATE TABLE IF NOT EXISTS coaching_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id INTEGER NOT NULL REFERENCES members(id),
    kind TEXT NOT NULL,  -- observation, star_assessment, conversation_plan
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Schedules
CREATE TABLE IF NOT EXISTS schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    command TEXT NOT NULL,
    cron_expr TEXT NOT NULL,
    last_run TEXT,
    next_run TEXT,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    """Open a connection with WAL mode and foreign keys enabled."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(db_path: Path) -> sqlite3.Connection:
    """Create the database and apply the schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)

    # Check current version
    try:
        row = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        current = row[0] if row and row[0] else 0
    except sqlite3.OperationalError:
        current = 0

    if current < SCHEMA_VERSION:
        conn.executescript(_SCHEMA_SQL)
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (SCHEMA_VERSION,),
        )
        conn.commit()

    return conn


def check_db(db_path: Path) -> dict:
    """Health check — returns table counts and version."""
    if not db_path.exists():
        return {"ok": False, "error": "Database not found"}

    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        version = row[0] if row and row[0] else 0
    except sqlite3.OperationalError:
        return {"ok": False, "error": "Schema not initialized"}

    tables = [
        "members", "member_flags", "teams", "team_members",
        "meetings", "meeting_items", "goals",
        "performance_snapshots", "coaching_entries", "schedules",
    ]
    counts = {}
    for table in tables:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        counts[table] = row[0]

    conn.close()
    return {
        "ok": True,
        "version": version,
        "tables": counts,
    }
