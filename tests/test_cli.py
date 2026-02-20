"""Tests for CLI commands via main() entry point."""

import json
import os
import sys
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest

from ascend.cli import main
from ascend.config import ASCEND_HOME, DB_PATH, CONFIG_PATH
from ascend.db import init_db


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Redirect ~/.ascend to a temp directory for all tests."""
    home = tmp_path / ".ascend"
    home.mkdir()
    monkeypatch.setattr("ascend.config.ASCEND_HOME", home)
    monkeypatch.setattr("ascend.config.CONFIG_PATH", home / "config.yaml")
    monkeypatch.setattr("ascend.config.DB_PATH", home / "ascend.db")
    monkeypatch.setattr("ascend.config.HISTORY_DIR", home / "history")
    monkeypatch.setattr("ascend.config.TRANSCRIPTS_DIR", home / "transcripts")
    monkeypatch.setattr("ascend.config.SCHEDULES_DIR", home / "schedules")
    # Also patch the command modules that import these at module level
    monkeypatch.setattr("ascend.commands.init.ASCEND_HOME", home)
    monkeypatch.setattr("ascend.commands.init.CONFIG_PATH", home / "config.yaml")
    monkeypatch.setattr("ascend.commands.init.DB_PATH", home / "ascend.db")
    monkeypatch.setattr("ascend.commands.init.HISTORY_DIR", home / "history")
    monkeypatch.setattr("ascend.commands.init.TRANSCRIPTS_DIR", home / "transcripts")
    monkeypatch.setattr("ascend.commands.init.SCHEDULES_DIR", home / "schedules")
    monkeypatch.setattr("ascend.commands.roster.DB_PATH", home / "ascend.db")
    monkeypatch.setattr("ascend.commands.team.DB_PATH", home / "ascend.db")
    monkeypatch.setattr("ascend.commands.meeting.DB_PATH", home / "ascend.db")
    monkeypatch.setattr("ascend.commands.meeting.TRANSCRIPTS_DIR", home / "transcripts")
    monkeypatch.setattr("ascend.audit.HISTORY_DIR", home / "history")
    return home


def _capture(argv):
    """Run CLI with given args and capture stdout."""
    buf = StringIO()
    with patch("sys.stdout", buf):
        main(argv)
    return buf.getvalue()


def _capture_json(argv):
    """Run CLI with --json and parse output."""
    output = _capture(argv + ["--json"])
    return json.loads(output)


class TestInit:
    def test_init(self, isolated_home):
        output = _capture(["init"])
        assert "initialized" in output.lower() or "Ascend" in output

    def test_init_json(self, isolated_home):
        data = _capture_json(["init"])
        assert data["status"] == "initialized"

    def test_init_creates_db(self, isolated_home):
        _capture(["init"])
        assert (isolated_home / "ascend.db").exists()

    def test_init_creates_config(self, isolated_home):
        _capture(["init"])
        assert (isolated_home / "config.yaml").exists()


class TestDoctor:
    def test_doctor_after_init(self, isolated_home):
        _capture(["init"])
        output = _capture(["doctor"])
        assert "Config file" in output
        assert "Database" in output

    def test_doctor_json(self, isolated_home):
        _capture(["init"])
        data = _capture_json(["doctor"])
        assert "checks" in data
        names = [c["name"] for c in data["checks"]]
        assert "Config file" in names
        assert "Database" in names


class TestConfig:
    def test_config_show(self, isolated_home):
        _capture(["init"])
        output = _capture(["config", "show"])
        assert "repos_dir" in output
        assert "model" in output

    def test_config_show_json(self, isolated_home):
        _capture(["init"])
        data = _capture_json(["config", "show"])
        assert "model" in data
        assert "repos_dir" in data

    def test_config_set(self, isolated_home):
        _capture(["init"])
        output = _capture(["config", "set", "model", "test-model"])
        assert "test-model" in output

    def test_config_set_persists(self, isolated_home):
        _capture(["init"])
        _capture(["config", "set", "model", "persisted-model"])
        data = _capture_json(["config", "show"])
        assert data["model"] == "persisted-model"


class TestRoster:
    def _init(self):
        _capture(["init"])

    def test_roster_list_empty(self, isolated_home):
        self._init()
        output = _capture(["roster", "list"])
        assert "No members" in output

    def test_roster_add_and_list(self, isolated_home):
        self._init()
        _capture(["roster", "add", "Alice", "--github", "alice", "--email", "alice@test.com"])
        output = _capture(["roster", "list"])
        assert "Alice" in output
        assert "alice" in output

    def test_roster_add_json(self, isolated_home):
        self._init()
        data = _capture_json(["roster", "add", "Bob", "--github", "bob"])
        assert data["name"] == "Bob"
        assert "id" in data

    def test_roster_show(self, isolated_home):
        self._init()
        _capture(["roster", "add", "Alice", "--github", "alice", "--title", "Engineer"])
        output = _capture(["roster", "show", "alice"])
        assert "Alice" in output
        assert "Engineer" in output

    def test_roster_show_json(self, isolated_home):
        self._init()
        _capture(["roster", "add", "Alice", "--github", "alice"])
        data = _capture_json(["roster", "show", "alice"])
        assert data["name"] == "Alice"
        assert data["github"] == "alice"

    def test_roster_edit(self, isolated_home):
        self._init()
        _capture(["roster", "add", "Alice", "--github", "alice"])
        _capture(["roster", "edit", "alice", "--title", "Senior Engineer"])
        data = _capture_json(["roster", "show", "alice"])
        assert data["title"] == "Senior Engineer"

    def test_roster_flag_unflag(self, isolated_home):
        self._init()
        _capture(["roster", "add", "Alice", "--github", "alice"])
        _capture(["roster", "flag", "alice", "oncall"])
        data = _capture_json(["roster", "show", "alice"])
        assert "oncall" in data["flags"]

        _capture(["roster", "unflag", "alice", "oncall"])
        data = _capture_json(["roster", "show", "alice"])
        assert "oncall" not in data["flags"]

    def test_roster_search(self, isolated_home):
        self._init()
        _capture(["roster", "add", "Alice Smith", "--github", "alice"])
        _capture(["roster", "add", "Bob Jones", "--github", "bob"])
        output = _capture(["roster", "search", "alice"])
        assert "Alice" in output
        assert "Bob" not in output

    def test_roster_search_json(self, isolated_home):
        self._init()
        _capture(["roster", "add", "Alice", "--github", "alice"])
        data = _capture_json(["roster", "search", "alice"])
        assert len(data) == 1
        assert data[0]["name"] == "Alice"

    def test_roster_import_csv(self, isolated_home, tmp_path):
        self._init()
        csv_file = tmp_path / "team.csv"
        csv_file.write_text(
            "Alice,Alice <alice@test.com>,@Alice,alice-gh\n"
            "Bob,Bob <bob@test.com>,@Bob,bob-gh\n"
        )
        output = _capture(["roster", "import", str(csv_file)])
        assert "Imported 2" in output

        data = _capture_json(["roster", "list"])
        assert len(data) == 2

    def test_roster_duplicate_github_rejected(self, isolated_home):
        self._init()
        _capture(["roster", "add", "Alice", "--github", "alice"])
        output = _capture(["roster", "add", "Alice2", "--github", "alice"])
        assert "already exists" in output


class TestTeam:
    def _init_with_members(self):
        _capture(["init"])
        _capture(["roster", "add", "Alice", "--github", "alice"])
        _capture(["roster", "add", "Bob", "--github", "bob"])

    def test_team_list_empty(self, isolated_home):
        _capture(["init"])
        output = _capture(["team", "list"])
        assert "No teams" in output

    def test_team_create_and_list(self, isolated_home):
        self._init_with_members()
        _capture(["team", "create", "Backend", "--description", "Backend team"])
        output = _capture(["team", "list"])
        assert "Backend" in output

    def test_team_create_json(self, isolated_home):
        _capture(["init"])
        data = _capture_json(["team", "create", "Frontend"])
        assert data["name"] == "Frontend"
        assert "id" in data

    def test_team_add_and_show(self, isolated_home):
        self._init_with_members()
        _capture(["team", "create", "Backend"])
        _capture(["team", "add", "Backend", "alice", "--role", "lead"])
        _capture(["team", "add", "Backend", "bob"])
        output = _capture(["team", "show", "Backend"])
        assert "Alice" in output
        assert "Bob" in output
        assert "lead" in output

    def test_team_show_json(self, isolated_home):
        self._init_with_members()
        _capture(["team", "create", "Backend"])
        _capture(["team", "add", "Backend", "alice"])
        data = _capture_json(["team", "show", "Backend"])
        assert data["name"] == "Backend"
        assert len(data["members"]) == 1

    def test_team_duplicate_rejected(self, isolated_home):
        _capture(["init"])
        _capture(["team", "create", "Backend"])
        output = _capture(["team", "create", "Backend"])
        assert "already exists" in output


class TestMeeting:
    """Phase 2 — Meeting / transcript commands."""

    def _init_with_member(self):
        _capture(["init"])
        _capture(["roster", "add", "Dana Sterling", "--github", "dana"])

    def _write_transcript(self, tmp_path, name="2025-01-15_Dana_Sterling.txt", content=None):
        d = tmp_path / "transcripts"
        d.mkdir(exist_ok=True)
        f = d / name
        f.write_text(content or (
            "Manager: Hey Dana, how's the backend service going?\n"
            "Dana Sterling: Good progress this week. We got the core schema finalized.\n"
            "Manager: Nice. Any blockers?\n"
            "Dana Sterling: The main concern is the database connection pooling.\n"
        ))
        return f

    # -- ingest --

    def test_ingest_single_file(self, isolated_home, tmp_path):
        self._init_with_member()
        f = self._write_transcript(tmp_path)
        output = _capture(["meeting", "ingest", str(f), "--no-llm"])
        assert "Ingested" in output
        assert "1 ingested" in output

    def test_ingest_json(self, isolated_home, tmp_path):
        self._init_with_member()
        f = self._write_transcript(tmp_path)
        data = _capture_json(["meeting", "ingest", str(f), "--no-llm"])
        assert len(data["ingested"]) == 1
        assert data["ingested"][0]["file"] == "2025-01-15_Dana_Sterling.txt"
        assert data["ingested"][0]["date"] == "2025-01-15"

    def test_ingest_duplicate_skipped(self, isolated_home, tmp_path):
        self._init_with_member()
        f = self._write_transcript(tmp_path)
        _capture(["meeting", "ingest", str(f), "--no-llm"])
        output = _capture(["meeting", "ingest", str(f), "--no-llm"])
        assert "already ingested" in output
        assert "0 ingested" in output

    def test_ingest_dry_run(self, isolated_home, tmp_path):
        self._init_with_member()
        f = self._write_transcript(tmp_path)
        output = _capture(["meeting", "ingest", str(f), "--no-llm", "--dry-run"])
        assert "dry-run" in output
        # Should NOT have actually ingested
        output2 = _capture(["meeting", "list"])
        assert "No meetings" in output2

    def test_ingest_directory(self, isolated_home, tmp_path):
        self._init_with_member()
        d = tmp_path / "transcripts"
        d.mkdir(exist_ok=True)
        (d / "2025-01-15_Dana_Sterling.txt").write_text(
            "Manager: Hello\nDana Sterling: Hi\n"
        )
        (d / "2025-01-20_Dana_Sterling.txt").write_text(
            "Manager: Checking in\nDana Sterling: All good\n"
        )
        output = _capture(["meeting", "ingest", str(d), "--no-llm"])
        assert "2 ingested" in output

    def test_ingest_missing_path(self, isolated_home):
        _capture(["init"])
        output = _capture(["meeting", "ingest", "/nonexistent/file.txt", "--no-llm"])
        assert "Error" in output or "not found" in output

    def test_ingest_resolves_member(self, isolated_home, tmp_path):
        self._init_with_member()
        f = self._write_transcript(tmp_path)
        data = _capture_json(["meeting", "ingest", str(f), "--no-llm"])
        assert data["ingested"][0]["member_id"] is not None

    def test_ingest_explicit_member(self, isolated_home, tmp_path):
        self._init_with_member()
        _capture(["roster", "add", "Bob", "--github", "bob"])
        f = self._write_transcript(tmp_path)
        data = _capture_json(["meeting", "ingest", str(f), "--no-llm", "--member", "Bob"])
        assert data["ingested"][0]["member_id"] is not None

    # -- list --

    def test_list_empty(self, isolated_home):
        _capture(["init"])
        output = _capture(["meeting", "list"])
        assert "No meetings" in output

    def test_list_after_ingest(self, isolated_home, tmp_path):
        self._init_with_member()
        f = self._write_transcript(tmp_path)
        _capture(["meeting", "ingest", str(f), "--no-llm"])
        output = _capture(["meeting", "list"])
        assert "Dana Sterling" in output
        assert "2025-01-15" in output

    def test_list_json(self, isolated_home, tmp_path):
        self._init_with_member()
        f = self._write_transcript(tmp_path)
        _capture(["meeting", "ingest", str(f), "--no-llm"])
        data = _capture_json(["meeting", "list"])
        assert len(data) == 1
        assert data[0]["member_name"] == "Dana Sterling"

    def test_list_filter_member(self, isolated_home, tmp_path):
        self._init_with_member()
        _capture(["roster", "add", "Bob", "--github", "bob"])
        f = self._write_transcript(tmp_path)
        _capture(["meeting", "ingest", str(f), "--no-llm"])
        # Filter by member that has no meetings
        output = _capture(["meeting", "list", "--member", "Bob"])
        assert "No meetings" in output
        # Filter by member that has meetings
        output2 = _capture(["meeting", "list", "--member", "Dana Sterling"])
        assert "Dana Sterling" in output2

    # -- show --

    def test_show(self, isolated_home, tmp_path):
        self._init_with_member()
        f = self._write_transcript(tmp_path)
        _capture(["meeting", "ingest", str(f), "--no-llm"])
        output = _capture(["meeting", "show", "1"])
        assert "Meeting 1" in output
        assert "2025-01-15" in output
        assert "Dana Sterling" in output
        assert "database" in output

    def test_show_json(self, isolated_home, tmp_path):
        self._init_with_member()
        f = self._write_transcript(tmp_path)
        _capture(["meeting", "ingest", str(f), "--no-llm"])
        data = _capture_json(["meeting", "show", "1"])
        assert data["id"] == 1
        assert data["member_name"] == "Dana Sterling"
        assert "raw_text" in data

    def test_show_not_found(self, isolated_home):
        _capture(["init"])
        output = _capture(["meeting", "show", "999"])
        assert "not found" in output

    # -- search --

    def test_search(self, isolated_home, tmp_path):
        self._init_with_member()
        f = self._write_transcript(tmp_path)
        _capture(["meeting", "ingest", str(f), "--no-llm"])
        output = _capture(["meeting", "search", "database"])
        assert "Meeting 1" in output

    def test_search_no_results(self, isolated_home, tmp_path):
        self._init_with_member()
        f = self._write_transcript(tmp_path)
        _capture(["meeting", "ingest", str(f), "--no-llm"])
        output = _capture(["meeting", "search", "kubernetes"])
        assert "No results" in output

    def test_search_json(self, isolated_home, tmp_path):
        self._init_with_member()
        f = self._write_transcript(tmp_path)
        _capture(["meeting", "ingest", str(f), "--no-llm"])
        data = _capture_json(["meeting", "search", "database"])
        assert len(data) >= 1
        assert data[0]["member_name"] == "Dana Sterling"

    # -- items --

    def test_items_empty(self, isolated_home):
        _capture(["init"])
        output = _capture(["meeting", "items"])
        assert "No open items" in output

    # -- item-close --

    def test_item_close_not_found(self, isolated_home):
        _capture(["init"])
        output = _capture(["meeting", "item-close", "999"])
        assert "not found" in output


class TestTranscriptParser:
    """Unit tests for transcript parsing logic."""

    def test_parse_transcript(self, tmp_path):
        f = tmp_path / "2025-03-01_Alice_Jones.txt"
        f.write_text("Manager: Hello\nAlice Jones: Hi there\n")
        from ascend.transcript import parse_transcript
        result = parse_transcript(f)
        assert result.source_file == "2025-03-01_Alice_Jones.txt"
        assert result.date == "2025-03-01"
        assert result.member_name == "Alice Jones"
        assert len(result.turns) == 2
        assert result.turns[0].speaker == "Manager"
        assert result.turns[1].speaker == "Alice Jones"

    def test_parse_file_not_found(self, tmp_path):
        from ascend.transcript import parse_transcript, TranscriptError
        with pytest.raises(TranscriptError) as exc_info:
            parse_transcript(tmp_path / "nope.txt")
        assert exc_info.value.variant == TranscriptError.FILE_NOT_FOUND

    def test_parse_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        from ascend.transcript import parse_transcript, TranscriptError
        with pytest.raises(TranscriptError) as exc_info:
            parse_transcript(f)
        assert exc_info.value.variant == TranscriptError.EMPTY_TRANSCRIPT

    def test_detect_date_from_filename(self):
        from ascend.transcript import detect_date
        assert detect_date("2025-06-15_John.txt", "") == "2025-06-15"

    def test_detect_date_from_content(self):
        from ascend.transcript import detect_date
        assert detect_date("notes.txt", "Meeting date: 2025-06-15\nHello") == "2025-06-15"

    def test_detect_date_invalid(self):
        from ascend.transcript import detect_date
        assert detect_date("notes.txt", "No date here") is None

    def test_scan_directory(self, tmp_path):
        (tmp_path / "a.txt").write_text("content")
        (tmp_path / "b.md").write_text("content")
        (tmp_path / "c.py").write_text("content")  # ignored
        (tmp_path / ".hidden.txt").write_text("content")  # ignored
        from ascend.transcript import scan_directory
        result = scan_directory(tmp_path)
        names = [p.name for p in result]
        assert "a.txt" in names
        assert "b.md" in names
        assert "c.py" not in names
        assert ".hidden.txt" not in names

    def test_check_duplicate(self, isolated_home):
        from ascend.db import init_db
        from ascend.transcript import check_duplicate
        conn = init_db(isolated_home / "ascend.db")
        conn.execute("INSERT INTO members (name) VALUES ('Test')")
        conn.commit()
        assert check_duplicate("test.txt", 1, "2025-01-01", conn) is False
        conn.execute(
            "INSERT INTO meetings (member_id, date, source_file, raw_text) VALUES (1, '2025-01-01', 'test.txt', 'hello')"
        )
        conn.commit()
        assert check_duplicate("test.txt", 1, "2025-01-01", conn) is True
        conn.close()
