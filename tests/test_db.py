"""Tests for SQLite database layer."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from ascend.db import SCHEMA_VERSION, check_db, get_connection, init_db


@pytest.fixture
def tmp_db(tmp_path):
    """Provide a temporary database path."""
    return tmp_path / "test.db"


def test_init_db_creates_file(tmp_db):
    conn = init_db(tmp_db)
    assert tmp_db.exists()
    conn.close()


def test_init_db_creates_tables(tmp_db):
    conn = init_db(tmp_db)
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall()
    ]
    assert "members" in tables
    assert "teams" in tables
    assert "meetings" in tables
    assert "member_flags" in tables
    assert "team_members" in tables
    assert "meeting_items" in tables
    assert "goals" in tables
    assert "performance_snapshots" in tables
    assert "coaching_entries" in tables
    assert "schedules" in tables
    conn.close()


def test_init_db_sets_schema_version(tmp_db):
    conn = init_db(tmp_db)
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    assert row[0] == SCHEMA_VERSION
    conn.close()


def test_init_db_idempotent(tmp_db):
    conn1 = init_db(tmp_db)
    conn1.close()
    conn2 = init_db(tmp_db)
    row = conn2.execute("SELECT COUNT(*) FROM schema_version").fetchone()
    # Should have exactly one version entry (not re-applied)
    assert row[0] == 1
    conn2.close()


def test_check_db_healthy(tmp_db):
    conn = init_db(tmp_db)
    conn.close()
    result = check_db(tmp_db)
    assert result["ok"] is True
    assert result["version"] == SCHEMA_VERSION
    assert "tables" in result
    assert result["tables"]["members"] == 0


def test_check_db_missing():
    result = check_db(Path("/nonexistent/path/db.sqlite"))
    assert result["ok"] is False


def test_foreign_keys_enabled(tmp_db):
    conn = init_db(tmp_db)
    row = conn.execute("PRAGMA foreign_keys").fetchone()
    assert row[0] == 1
    conn.close()


def test_wal_mode(tmp_db):
    conn = init_db(tmp_db)
    row = conn.execute("PRAGMA journal_mode").fetchone()
    assert row[0] == "wal"
    conn.close()


def test_fts5_table_created(tmp_db):
    conn = init_db(tmp_db)
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='meetings_fts'"
        ).fetchall()
    ]
    assert "meetings_fts" in tables
    conn.close()


def test_insert_member(tmp_db):
    conn = init_db(tmp_db)
    conn.execute(
        "INSERT INTO members (name, email, github) VALUES (?, ?, ?)",
        ("Test User", "test@example.com", "testuser"),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM members WHERE github = 'testuser'").fetchone()
    assert row["name"] == "Test User"
    assert row["email"] == "test@example.com"
    assert row["status"] == "active"
    conn.close()


def test_member_flags(tmp_db):
    conn = init_db(tmp_db)
    conn.execute("INSERT INTO members (name) VALUES ('Test')")
    conn.execute("INSERT INTO member_flags (member_id, flag) VALUES (1, 'oncall')")
    conn.commit()
    flags = conn.execute("SELECT flag FROM member_flags WHERE member_id = 1").fetchall()
    assert len(flags) == 1
    assert flags[0]["flag"] == "oncall"
    conn.close()


def test_unique_github_constraint(tmp_db):
    conn = init_db(tmp_db)
    conn.execute("INSERT INTO members (name, github) VALUES ('A', 'same')")
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("INSERT INTO members (name, github) VALUES ('B', 'same')")
    conn.close()
