"""Tests for Phase 3 — Integrations & Sync."""

import json
import os
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ascend.cli import main
from ascend.db import init_db


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Redirect ~/.ascend to a temp directory."""
    home = tmp_path / ".ascend"
    home.mkdir()
    monkeypatch.setattr("ascend.config.ASCEND_HOME", home)
    monkeypatch.setattr("ascend.config.CONFIG_PATH", home / "config.yaml")
    monkeypatch.setattr("ascend.config.DB_PATH", home / "ascend.db")
    monkeypatch.setattr("ascend.config.HISTORY_DIR", home / "history")
    monkeypatch.setattr("ascend.config.TRANSCRIPTS_DIR", home / "transcripts")
    monkeypatch.setattr("ascend.config.SCHEDULES_DIR", home / "schedules")
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
    monkeypatch.setattr("ascend.commands.sync.DB_PATH", home / "ascend.db")
    monkeypatch.setattr("ascend.audit.HISTORY_DIR", home / "history")
    return home


def _capture(argv):
    buf = StringIO()
    with patch("sys.stdout", buf):
        main(argv)
    return buf.getvalue()


def _capture_json(argv):
    output = _capture(argv + ["--json"])
    return json.loads(output)


class TestGitHubFetcher:
    """Unit tests for GitHub fetcher with mocked subprocess."""

    def test_run_cmd_success(self):
        from ascend.integrations.github import _run_cmd
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="output", stderr="", returncode=0)
            stdout, stderr, rc = _run_cmd(["echo", "hello"])
            assert rc == 0
            assert stdout == "output"

    def test_run_cmd_timeout_retry(self):
        from subprocess import TimeoutExpired
        from ascend.integrations.github import _run_cmd
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [TimeoutExpired("cmd", 15), MagicMock(stdout="ok", stderr="", returncode=0)]
            stdout, _, rc = _run_cmd(["cmd"], max_retries=1)
            assert rc == 0
            assert stdout == "ok"

    def test_fetch_commits_repo_not_found(self):
        from ascend.integrations.github import fetch_commits
        result = fetch_commits("/nonexistent", "repo", "dev", datetime.now(timezone.utc))
        assert result["error"] is not None
        assert result["data"] == []

    def test_fetch_commits_parses_output(self, tmp_path):
        from ascend.integrations.github import fetch_commits
        repo = tmp_path / "myrepo"
        repo.mkdir()
        git_output = "abc12345678|Alice|Fix bug|2025-01-15T10:00:00+00:00\ndef98765432|Bob|Add feature|2025-01-15T11:00:00+00:00\n"
        with patch("ascend.integrations.github._run_cmd") as mock_cmd:
            mock_cmd.side_effect = [
                ("", "", 0),  # git fetch
                (git_output, "", 0),  # git log
            ]
            result = fetch_commits(str(tmp_path), "myrepo", "dev", datetime.now(timezone.utc))
        assert result["error"] is None
        assert len(result["data"]) == 2
        assert result["data"][0]["hash"] == "abc12345"
        assert result["data"][0]["author"] == "Alice"
        assert result["data"][1]["hash"] == "def98765"

    def test_fetch_prs_parses_json(self):
        from ascend.integrations.github import fetch_prs
        pr_json = json.dumps([
            {"number": 42, "title": "Fix", "author": {"login": "alice"},
             "state": "OPEN", "reviewDecision": "APPROVED",
             "createdAt": "2025-01-15T10:00:00Z", "mergedAt": None, "url": "https://github.com/pr/42"}
        ])
        with patch("ascend.integrations.github._run_cmd") as mock_cmd:
            mock_cmd.side_effect = [
                (pr_json, "", 0),  # open PRs
                ("[]", "", 0),  # merged PRs
            ]
            result = fetch_prs("org/repo", datetime(2025, 1, 10, tzinfo=timezone.utc))
        assert result["error"] is None
        assert len(result["open"]) == 1
        assert result["open"][0]["number"] == 42
        assert result["open"][0]["review_status"] == "approved"

    def test_review_label_mapping(self):
        from ascend.integrations.github import _review_label
        assert _review_label("APPROVED") == "approved"
        assert _review_label("CHANGES_REQUESTED") == "changes requested"
        assert _review_label(None) == "needs review"
        assert _review_label("") == "needs review"


class TestLinearFetcher:
    """Unit tests for Linear fetcher with mocked urllib."""

    def test_graphql_success(self):
        from ascend.integrations.linear import _graphql
        response_body = json.dumps({"data": {"issues": {"nodes": []}}}).encode()
        mock_response = MagicMock()
        mock_response.read.return_value = response_body
        with patch("ascend.integrations.linear.urlopen", return_value=mock_response):
            result = _graphql("api-key", "query { test }", {})
        assert result is not None
        assert "issues" in result

    def test_graphql_returns_none_on_error(self):
        from urllib.error import URLError
        from ascend.integrations.linear import _graphql
        with patch("ascend.integrations.linear.urlopen", side_effect=URLError("fail")):
            result = _graphql("api-key", "query { test }", {}, max_retries=0)
        assert result is None

    def test_fetch_recent_issues_pagination(self):
        from ascend.integrations.linear import fetch_recent_issues
        page1 = {"issues": {
            "nodes": [{"identifier": "SVC-1", "title": "Test"}],
            "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
        }}
        page2 = {"issues": {
            "nodes": [{"identifier": "SVC-2", "title": "Test2"}],
            "pageInfo": {"hasNextPage": False, "endCursor": None},
        }}
        with patch("ascend.integrations.linear._graphql", side_effect=[page1, page2]):
            issues = fetch_recent_issues("key", "team-id", datetime(2025, 1, 1, tzinfo=timezone.utc))
        assert len(issues) == 2
        assert issues[0]["identifier"] == "SVC-1"
        assert issues[1]["identifier"] == "SVC-2"

    def test_match_issues_by_label(self):
        from ascend.integrations.linear import match_issues
        issues = [
            {"title": "Something", "labels": {"nodes": [{"name": "pricing"}]}, "assignee": None},
            {"title": "Other", "labels": {"nodes": [{"name": "sync"}]}, "assignee": None},
        ]
        matched = match_issues(issues, ["pricing"])
        assert len(matched) == 1
        assert matched[0]["title"] == "Something"

    def test_match_issues_by_assignee(self):
        from ascend.integrations.linear import match_issues
        issues = [
            {"title": "Task", "labels": {"nodes": []},
             "assignee": {"name": "Dana", "displayName": "Dana Sterling"}},
        ]
        matched = match_issues(issues, ["pricing"], assignees=["Dana Sterling"])
        assert len(matched) == 1

    def test_get_effective_team_ids_merge(self):
        from ascend.integrations.linear import get_effective_team_ids
        config = MagicMock()
        config.linear_team_id = "team-a"
        config.linear_team_ids = ["team-b", "team-c"]
        result = get_effective_team_ids(config)
        assert result == ["team-a", "team-b", "team-c"]

    def test_get_effective_team_ids_no_duplicate(self):
        from ascend.integrations.linear import get_effective_team_ids
        config = MagicMock()
        config.linear_team_id = "team-b"
        config.linear_team_ids = ["team-b", "team-c"]
        result = get_effective_team_ids(config)
        assert result == ["team-b", "team-c"]


class TestSlackFetcher:
    """Unit tests for Slack fetcher with mocked urllib."""

    def test_detect_signals(self):
        from ascend.integrations.slack import detect_signals
        signals = detect_signals("There's a critical bug blocking the release")
        assert "critical" in signals
        assert "bug" in signals
        assert "blocking" not in signals  # "blocking" != "blocker"

    def test_detect_signals_none(self):
        from ascend.integrations.slack import detect_signals
        assert detect_signals("Everything is working great") == []

    def test_fetch_channel_no_token(self):
        from ascend.integrations.slack import fetch_channel_activity
        result = fetch_channel_activity("", "general", datetime.now(timezone.utc))
        assert result["error"] is not None
        assert result["message_count"] == 0

    def test_fetch_channel_no_channel(self):
        from ascend.integrations.slack import fetch_channel_activity
        result = fetch_channel_activity("token", "", datetime.now(timezone.utc))
        assert result["error"] is not None


class TestSnapshot:
    """Unit tests for performance snapshot."""

    def test_take_snapshot_no_apis(self, isolated_home, monkeypatch):
        from ascend.config import AscendConfig
        from ascend.integrations.snapshot import take_snapshot
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        conn = init_db(isolated_home / "ascend.db")
        conn.execute("INSERT INTO members (name, github, status) VALUES ('Alice', 'alice', 'active')")
        conn.commit()
        config = AscendConfig()
        # repos_dir doesn't exist — github will return error, linear key not set
        result = take_snapshot(1, "Alice", "alice", conn, config)
        assert result["member_name"] == "Alice"
        assert result["score"] >= 0
        # Linear API key is not set, so at least that error
        assert any("linear" in e for e in result["errors"])
        conn.close()

    def test_take_snapshot_with_github_data(self, isolated_home):
        from ascend.config import AscendConfig
        from ascend.integrations.snapshot import take_snapshot
        conn = init_db(isolated_home / "ascend.db")
        conn.execute("INSERT INTO members (name, github, status) VALUES ('Alice', 'alice', 'active')")
        conn.commit()
        config = AscendConfig()

        mock_gh = {
            "error": None,
            "commits": [{"hash": "abc"}, {"hash": "def"}],
            "prs": {"open": [{"number": 1}], "merged": [{"number": 2}]},
        }
        with patch("ascend.integrations.github.fetch_member_github", return_value=mock_gh):
            result = take_snapshot(1, "Alice", "alice", conn, config)
        assert result["metrics"]["commits_count"] == 2
        assert result["metrics"]["prs_opened"] == 1
        assert result["metrics"]["prs_merged"] == 1
        # Score: 2*1 + 1*3 + 1*5 = 10
        assert result["score"] == 10.0
        conn.close()

    def test_snapshot_stored_in_db(self, isolated_home):
        from ascend.config import AscendConfig
        from ascend.integrations.snapshot import take_snapshot
        conn = init_db(isolated_home / "ascend.db")
        conn.execute("INSERT INTO members (name, github, status) VALUES ('Alice', 'alice', 'active')")
        conn.commit()
        config = AscendConfig()

        mock_gh = {"error": None, "commits": [], "prs": {"open": [], "merged": []}}
        with patch("ascend.integrations.github.fetch_member_github", return_value=mock_gh):
            take_snapshot(1, "Alice", "alice", conn, config)
        row = conn.execute("SELECT * FROM performance_snapshots WHERE member_id = 1").fetchone()
        assert row is not None
        assert row["source"] == "sync"
        conn.close()


class TestSyncCLI:
    """Integration tests for sync CLI commands."""

    def _init_with_member(self):
        _capture(["init"])
        _capture(["roster", "add", "Alice", "--github", "alice"])

    def test_sync_github_no_member(self, isolated_home):
        self._init_with_member()
        mock_gh = {"error": None, "commits": [], "prs": {"open": [], "merged": []}}
        with patch("ascend.integrations.github.fetch_member_github", return_value=mock_gh):
            data = _capture_json(["sync", "github"])
        assert data["error"] is None

    def test_sync_github_member_filter(self, isolated_home):
        self._init_with_member()
        mock_gh = {"error": None, "commits": [{"hash": "abc"}], "prs": {"open": [], "merged": []}}
        with patch("ascend.integrations.github.fetch_member_github", return_value=mock_gh):
            data = _capture_json(["sync", "github", "--member", "Alice"])
        assert data["error"] is None
        assert len(data["results"]) == 1
        assert data["results"][0]["member"] == "Alice"

    def test_sync_linear_no_key(self, isolated_home, monkeypatch):
        self._init_with_member()
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        data = _capture_json(["sync", "linear"])
        assert "not set" in data["error"]

    def test_sync_slack_no_key(self, isolated_home, monkeypatch):
        self._init_with_member()
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        data = _capture_json(["sync", "slack"])
        assert "not set" in data["error"]

    def test_sync_snapshot_json(self, isolated_home):
        self._init_with_member()
        mock_gh = {"error": None, "commits": [], "prs": {"open": [], "merged": []}}
        with patch("ascend.integrations.github.fetch_member_github", return_value=mock_gh):
            data = _capture_json(["sync", "snapshot"])
        assert len(data) == 1
        assert data[0]["member_name"] == "Alice"

    def test_sync_snapshot_member_filter(self, isolated_home):
        self._init_with_member()
        mock_gh = {"error": None, "commits": [], "prs": {"open": [], "merged": []}}
        with patch("ascend.integrations.github.fetch_member_github", return_value=mock_gh):
            data = _capture_json(["sync", "snapshot", "--member", "Alice"])
        assert len(data) == 1

    def test_sync_all_json(self, isolated_home, monkeypatch):
        self._init_with_member()
        monkeypatch.delenv("LINEAR_API_KEY", raising=False)
        monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
        mock_gh = {"error": None, "commits": [], "prs": {"open": [], "merged": []}}
        with patch("ascend.integrations.github.fetch_member_github", return_value=mock_gh):
            data = _capture_json(["sync"])
        assert "github" in data
        assert "linear" in data
        assert "slack" in data
        assert "snapshots" in data


class TestConfigExtension:
    """Test new config fields."""

    def test_new_config_fields(self, isolated_home):
        _capture(["init"])
        data = _capture_json(["config", "show"])
        assert "linear_api_key_env" in data
        assert data["linear_api_key_env"] == "LINEAR_API_KEY"
        assert "slack_bot_token_env" in data
        assert data["slack_bot_token_env"] == "SLACK_BOT_TOKEN"
        assert "linear_team_ids" in data
