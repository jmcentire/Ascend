"""Smoke tests for Ascend TUI."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def isolated_home(tmp_path):
    """Create isolated ~/.ascend with DB for TUI tests."""
    home = tmp_path / ".ascend"
    home.mkdir()
    db_path = home / "ascend.db"

    from ascend.db import init_db

    conn = init_db(db_path)

    # Seed test data
    conn.execute(
        "INSERT INTO members (name, email, github, title, status) VALUES (?, ?, ?, ?, ?)",
        ("Alice Test", "alice@test.com", "alicetest", "Senior Engineer", "active"),
    )
    conn.execute(
        "INSERT INTO members (name, email, github, title, status) VALUES (?, ?, ?, ?, ?)",
        ("Bob Test", "bob@test.com", "bobtest", "Staff Engineer", "active"),
    )
    conn.execute(
        "INSERT INTO member_flags (member_id, flag) VALUES (1, 'oncall')",
    )
    conn.execute(
        "INSERT INTO teams (name, description) VALUES (?, ?)",
        ("Platform", "Platform team"),
    )
    conn.execute(
        "INSERT INTO team_members (team_id, member_id, role) VALUES (1, 1, 'member')",
    )
    conn.execute(
        "INSERT INTO meetings (member_id, date, source, summary, sentiment_score) VALUES (?, ?, ?, ?, ?)",
        (1, "2026-02-18", "transcript", "Discussed project progress and roadmap", 0.75),
    )
    conn.execute(
        "INSERT INTO meeting_items (meeting_id, kind, content, status) VALUES (?, ?, ?, ?)",
        (1, "action_item", "Follow up on deployment", "open"),
    )
    conn.execute(
        """INSERT INTO schedules (name, command, cron_expr, enabled, next_run)
           VALUES (?, ?, ?, ?, ?)""",
        ("daily-sync", "sync", "0 9 * * *", 1, "2026-02-20 09:00"),
    )
    conn.commit()
    conn.close()

    return home, db_path


@pytest.mark.asyncio
async def test_app_mounts(isolated_home):
    """App should mount and show dashboard."""
    home, db_path = isolated_home

    with patch("ascend.config.DB_PATH", db_path), \
         patch("ascend.config.ASCEND_HOME", home):
        from ascend.tui.app import AscendApp

        app = AscendApp()
        async with app.run_test() as pilot:
            assert app.title == "Ascend"
            # Dashboard should be the initial panel
            assert app._active_panel == "dashboard"


@pytest.mark.asyncio
async def test_switch_to_roster(isolated_home):
    """Pressing 2 should switch to roster panel."""
    home, db_path = isolated_home

    with patch("ascend.config.DB_PATH", db_path), \
         patch("ascend.config.ASCEND_HOME", home):
        from ascend.tui.app import AscendApp

        app = AscendApp()
        async with app.run_test() as pilot:
            await pilot.press("2")
            assert app._active_panel == "roster"


@pytest.mark.asyncio
async def test_switch_to_meetings(isolated_home):
    """Pressing 3 should switch to meetings panel."""
    home, db_path = isolated_home

    with patch("ascend.config.DB_PATH", db_path), \
         patch("ascend.config.ASCEND_HOME", home):
        from ascend.tui.app import AscendApp

        app = AscendApp()
        async with app.run_test() as pilot:
            await pilot.press("3")
            assert app._active_panel == "meetings"


@pytest.mark.asyncio
async def test_switch_all_screens(isolated_home):
    """All screen switches via number keys should work."""
    home, db_path = isolated_home

    with patch("ascend.config.DB_PATH", db_path), \
         patch("ascend.config.ASCEND_HOME", home):
        from ascend.tui.app import AscendApp

        app = AscendApp()
        async with app.run_test() as pilot:
            for key, expected in [
                ("1", "dashboard"),
                ("2", "roster"),
                ("3", "meetings"),
                ("4", "reports"),
                ("5", "coaching"),
                ("6", "schedules"),
            ]:
                await pilot.press(key)
                assert app._active_panel == expected, f"Expected {expected} after pressing {key}"


@pytest.mark.asyncio
async def test_help_overlay(isolated_home):
    """Pressing ? should show help overlay."""
    home, db_path = isolated_home

    with patch("ascend.config.DB_PATH", db_path), \
         patch("ascend.config.ASCEND_HOME", home):
        from ascend.tui.app import AscendApp

        app = AscendApp()
        async with app.run_test() as pilot:
            await pilot.press("question_mark")
            # Help screen should be pushed
            assert len(app.screen_stack) > 1
            await pilot.press("escape")
            assert len(app.screen_stack) == 1


@pytest.mark.asyncio
async def test_refresh_action(isolated_home):
    """Pressing r should refresh without errors."""
    home, db_path = isolated_home

    with patch("ascend.config.DB_PATH", db_path), \
         patch("ascend.config.ASCEND_HOME", home):
        from ascend.tui.app import AscendApp

        app = AscendApp()
        async with app.run_test() as pilot:
            await pilot.press("r")  # Should not raise


@pytest.mark.asyncio
async def test_app_without_db(tmp_path):
    """App should handle missing DB gracefully."""
    fake_db = tmp_path / "nonexistent.db"

    with patch("ascend.config.DB_PATH", fake_db):
        from ascend.tui.app import AscendApp

        app = AscendApp()
        async with app.run_test() as pilot:
            # Should mount without crashing
            assert app.title == "Ascend"
