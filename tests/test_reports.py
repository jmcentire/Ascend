"""Tests for Phase 4 — Reports."""

import json
import os
from datetime import datetime, timedelta
from io import StringIO
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
    monkeypatch.setattr("ascend.commands.report.DB_PATH", home / "ascend.db")
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


def _init_with_member():
    _capture(["init"])
    _capture(["roster", "add", "Alice", "--github", "alice", "--title", "Engineer"])


def _init_with_team():
    _init_with_member()
    _capture(["roster", "add", "Bob", "--github", "bob", "--title", "Senior Engineer"])
    _capture(["team", "create", "Backend"])
    _capture(["team", "add", "Backend", "Alice"])
    _capture(["team", "add", "Backend", "Bob"])


def _add_snapshot(home, member_id, date_str, metrics, score):
    """Insert a snapshot directly into the DB."""
    from ascend.db import get_connection
    conn = get_connection(home / "ascend.db")
    conn.execute(
        """INSERT INTO performance_snapshots (member_id, date, source, metrics, score)
           VALUES (?, ?, 'sync', ?, ?)""",
        (member_id, date_str, json.dumps(metrics), score),
    )
    conn.commit()
    conn.close()


def _add_meeting(home, member_id, date_str, summary="Meeting notes", sentiment=0.7):
    """Insert a meeting directly into the DB."""
    from ascend.db import get_connection
    conn = get_connection(home / "ascend.db")
    conn.execute(
        """INSERT INTO meetings (member_id, date, source, raw_text, summary, sentiment_score)
           VALUES (?, ?, 'test', 'raw text', ?, ?)""",
        (member_id, date_str, summary, sentiment),
    )
    conn.commit()
    conn.close()


def _add_meeting_item(home, meeting_id, kind, content, status="open"):
    """Insert a meeting item directly into the DB."""
    from ascend.db import get_connection
    conn = get_connection(home / "ascend.db")
    conn.execute(
        "INSERT INTO meeting_items (meeting_id, kind, content, status) VALUES (?, ?, ?, ?)",
        (meeting_id, kind, content, status),
    )
    conn.commit()
    conn.close()


class TestReportPerformance:
    """Tests for report performance command."""

    def test_no_data(self, isolated_home):
        _init_with_member()
        data = _capture_json(["report", "performance", "--member", "Alice"])
        assert data["member"] == "Alice"
        assert data["snapshots_count"] == 0
        assert data["status"] == "No Data"
        assert data["metrics"]["commits_count"] == 0

    def test_with_snapshots(self, isolated_home):
        _init_with_member()
        today = datetime.now().strftime("%Y-%m-%d")
        _add_snapshot(isolated_home, 1, today, {
            "commits_count": 5, "prs_opened": 2, "prs_merged": 1,
            "issues_completed": 3, "issues_in_progress": 1,
        }, 20.0)
        data = _capture_json(["report", "performance", "--member", "Alice"])
        assert data["snapshots_count"] == 1
        assert data["metrics"]["commits_count"] == 5
        assert data["metrics"]["prs_merged"] == 1
        assert data["avg_score"] == 20.0
        assert data["status"] == "Active"

    def test_member_not_found(self, isolated_home):
        _init_with_member()
        data = _capture_json(["report", "performance", "--member", "Nobody"])
        assert "error" in data

    def test_all_members(self, isolated_home):
        _init_with_team()
        data = _capture_json(["report", "performance"])
        assert isinstance(data, list)
        assert len(data) == 2

    def test_team_filter(self, isolated_home):
        _init_with_team()
        data = _capture_json(["report", "performance", "--team", "Backend"])
        assert isinstance(data, list)
        assert len(data) == 2
        names = {d["member"] for d in data}
        assert "Alice" in names
        assert "Bob" in names

    def test_team_not_found(self, isolated_home):
        _init_with_member()
        data = _capture_json(["report", "performance", "--team", "Nonexistent"])
        assert "error" in data

    def test_text_output(self, isolated_home):
        _init_with_member()
        output = _capture(["report", "performance", "--member", "Alice"])
        assert "Performance Report" in output
        assert "Alice" in output
        assert "No Data" in output

    def test_with_meetings_and_items(self, isolated_home):
        _init_with_member()
        today = datetime.now().strftime("%Y-%m-%d")
        _add_meeting(isolated_home, 1, today, "Discussed project status", 0.8)
        _add_meeting_item(isolated_home, 1, "action_item", "Review PR #42")
        data = _capture_json(["report", "performance", "--member", "Alice"])
        assert data["meetings_count"] == 1
        assert data["avg_sentiment"] == 0.8
        assert data["open_items_count"] == 1
        assert data["open_items"][0]["content"] == "Review PR #42"

    def test_date_range(self, isolated_home):
        _init_with_member()
        _add_snapshot(isolated_home, 1, "2025-01-10", {
            "commits_count": 3, "prs_opened": 0, "prs_merged": 0,
            "issues_completed": 0, "issues_in_progress": 0,
        }, 3.0)
        _add_snapshot(isolated_home, 1, "2025-01-20", {
            "commits_count": 5, "prs_opened": 0, "prs_merged": 0,
            "issues_completed": 0, "issues_in_progress": 0,
        }, 5.0)
        data = _capture_json([
            "report", "performance", "--member", "Alice",
            "--from", "2025-01-15", "--to", "2025-01-25",
        ])
        assert data["snapshots_count"] == 1
        assert data["metrics"]["commits_count"] == 5

    def test_with_flags(self, isolated_home):
        _init_with_member()
        _capture(["roster", "flag", "Alice", "pto"])
        data = _capture_json(["report", "performance", "--member", "Alice"])
        assert "pto" in data["flags"]
        assert data["status"] == "PTO"


class TestReportTeam:
    """Tests for report team command."""

    def test_all_members(self, isolated_home):
        _init_with_team()
        data = _capture_json(["report", "team"])
        assert data["team"] == "All Members"
        assert data["member_count"] == 2

    def test_team_filter(self, isolated_home):
        _init_with_team()
        data = _capture_json(["report", "team", "--team", "Backend"])
        assert data["team"] == "Backend"
        assert data["member_count"] == 2

    def test_team_not_found(self, isolated_home):
        _init_with_member()
        data = _capture_json(["report", "team", "--team", "Nonexistent"])
        assert "error" in data

    def test_with_snapshot_data(self, isolated_home):
        _init_with_team()
        today = datetime.now().strftime("%Y-%m-%d")
        _add_snapshot(isolated_home, 1, today, {
            "commits_count": 5, "prs_opened": 2, "prs_merged": 1,
            "issues_completed": 3, "issues_in_progress": 0,
        }, 20.0)
        _add_snapshot(isolated_home, 2, today, {
            "commits_count": 3, "prs_opened": 1, "prs_merged": 2,
            "issues_completed": 1, "issues_in_progress": 1,
        }, 15.0)
        data = _capture_json(["report", "team", "--team", "Backend"])
        assert data["total_commits"] == 8
        assert data["total_prs_merged"] == 3
        assert data["total_issues_completed"] == 4
        assert len(data["members"]) == 2

    def test_text_output(self, isolated_home):
        _init_with_team()
        output = _capture(["report", "team", "--team", "Backend"])
        assert "Team Report" in output
        assert "Backend" in output
        assert "Alice" in output
        assert "Bob" in output


class TestReportProgress:
    """Tests for report progress command."""

    def test_no_data(self, isolated_home):
        _init_with_member()
        data = _capture_json(["report", "progress"])
        assert data["days_with_data"] == 0
        assert data["trend"] == []

    def test_with_trend_data(self, isolated_home):
        _init_with_member()
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        _add_snapshot(isolated_home, 1, yesterday, {
            "commits_count": 3, "prs_opened": 0, "prs_merged": 0,
            "issues_completed": 0, "issues_in_progress": 0,
        }, 3.0)
        _add_snapshot(isolated_home, 1, today, {
            "commits_count": 5, "prs_opened": 0, "prs_merged": 0,
            "issues_completed": 0, "issues_in_progress": 0,
        }, 5.0)
        data = _capture_json(["report", "progress"])
        assert data["days_with_data"] == 2
        assert len(data["trend"]) == 2
        assert data["trend"][0]["date"] == yesterday
        assert data["trend"][1]["date"] == today

    def test_member_filter(self, isolated_home):
        _init_with_member()
        data = _capture_json(["report", "progress", "--member", "Alice"])
        assert data["member_filter"] == "Alice"

    def test_member_not_found(self, isolated_home):
        _init_with_member()
        data = _capture_json(["report", "progress", "--member", "Nobody"])
        assert "error" in data

    def test_text_output_no_data(self, isolated_home):
        _init_with_member()
        output = _capture(["report", "progress"])
        assert "Progress Report" in output
        assert "No snapshot data" in output


class TestReportGit:
    """Tests for report git command."""

    def test_no_github_members(self, isolated_home):
        _capture(["init"])
        _capture(["roster", "add", "NoGH"])
        data = _capture_json(["report", "git"])
        assert data == []

    def test_with_github_data(self, isolated_home):
        _init_with_member()
        today = datetime.now().strftime("%Y-%m-%d")
        _add_snapshot(isolated_home, 1, today, {
            "commits_count": 10, "prs_opened": 3, "prs_merged": 2,
            "issues_completed": 0, "issues_in_progress": 0,
        }, 16.0)
        data = _capture_json(["report", "git"])
        assert len(data) == 1
        assert data[0]["member"] == "Alice"
        assert data[0]["github"] == "alice"
        assert data[0]["commits"] == 10
        assert data[0]["prs_merged"] == 2

    def test_member_filter(self, isolated_home):
        _init_with_member()
        data = _capture_json(["report", "git", "--member", "Alice"])
        assert len(data) == 1
        assert data[0]["member"] == "Alice"

    def test_member_not_found(self, isolated_home):
        _init_with_member()
        data = _capture_json(["report", "git", "--member", "Nobody"])
        assert "error" in data

    def test_text_output(self, isolated_home):
        _init_with_member()
        output = _capture(["report", "git"])
        assert "Git Report" in output


class TestReportDashboard:
    """Tests for report dashboard command."""

    def test_empty_dashboard(self, isolated_home):
        _capture(["init"])
        data = _capture_json(["report", "dashboard"])
        assert data["active_members"] == 0
        assert data["teams"] == 0
        assert data["total_commits"] == 0
        assert data["member_rankings"] == []

    def test_populated_dashboard(self, isolated_home):
        _init_with_team()
        today = datetime.now().strftime("%Y-%m-%d")
        _add_snapshot(isolated_home, 1, today, {
            "commits_count": 5, "prs_opened": 2, "prs_merged": 1,
            "issues_completed": 3, "issues_in_progress": 0,
        }, 20.0)
        _add_snapshot(isolated_home, 2, today, {
            "commits_count": 3, "prs_opened": 1, "prs_merged": 2,
            "issues_completed": 1, "issues_in_progress": 0,
        }, 15.0)
        _add_meeting(isolated_home, 1, today)
        data = _capture_json(["report", "dashboard"])
        assert data["active_members"] == 2
        assert data["teams"] == 1
        assert data["total_commits"] == 8
        assert data["total_prs_merged"] == 3
        assert data["total_issues_completed"] == 4
        assert data["meetings"] == 1
        assert len(data["member_rankings"]) == 2
        # Alice has higher score, should be first
        assert data["member_rankings"][0]["member"] == "Alice"
        assert data["member_rankings"][0]["avg_score"] == 20.0

    def test_text_output(self, isolated_home):
        _init_with_team()
        output = _capture(["report", "dashboard"])
        assert "Dashboard" in output
        assert "Active Members" in output


class TestReportCustom:
    """Tests for report custom command."""

    def test_no_api_key(self, isolated_home, monkeypatch):
        _init_with_member()
        monkeypatch.delenv("ASCEND_ANTHROPIC_API_KEY", raising=False)
        data = _capture_json(["report", "custom", "What are the top risks?"])
        assert "error" in data
        assert "API key" in data["error"]
        assert "context" in data

    def test_with_mocked_llm(self, isolated_home, monkeypatch):
        _init_with_member()
        today = datetime.now().strftime("%Y-%m-%d")
        _add_snapshot(isolated_home, 1, today, {
            "commits_count": 5, "prs_opened": 2, "prs_merged": 1,
            "issues_completed": 3, "issues_in_progress": 0,
        }, 20.0)
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="## Risk Report\n\nNo major risks.")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        with patch("ascend.summarizer.get_client", return_value=mock_client):
            data = _capture_json(["report", "custom", "What are the top risks?"])
        assert data["prompt"] == "What are the top risks?"
        assert "Risk Report" in data["report"]

    def test_member_filter(self, isolated_home, monkeypatch):
        _init_with_member()
        monkeypatch.delenv("ASCEND_ANTHROPIC_API_KEY", raising=False)
        data = _capture_json(["report", "custom", "Analyze Alice", "--member", "Alice"])
        assert "context" in data
        assert "Alice" in data["context"]

    def test_member_not_found(self, isolated_home):
        _init_with_member()
        data = _capture_json(["report", "custom", "Test", "--member", "Nobody"])
        assert "error" in data

    def test_llm_error(self, isolated_home):
        _init_with_member()
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API timeout")
        with patch("ascend.summarizer.get_client", return_value=mock_client):
            data = _capture_json(["report", "custom", "Test prompt"])
        assert "error" in data
        assert "API timeout" in data["error"]


class TestReportHelpers:
    """Tests for report helper functions."""

    def test_aggregate_metrics(self):
        from ascend.commands.report import _aggregate_metrics
        snapshots = [
            {"metrics": {"commits_count": 3, "prs_opened": 1, "prs_merged": 0,
                         "issues_completed": 2, "issues_in_progress": 1}},
            {"metrics": {"commits_count": 5, "prs_opened": 2, "prs_merged": 1,
                         "issues_completed": 1, "issues_in_progress": 0}},
        ]
        totals = _aggregate_metrics(snapshots)
        assert totals["commits_count"] == 8
        assert totals["prs_opened"] == 3
        assert totals["prs_merged"] == 1
        assert totals["issues_completed"] == 3

    def test_compute_velocity_empty(self):
        from ascend.commands.report import _compute_velocity
        assert _compute_velocity([]) == 0.0

    def test_compute_velocity_with_data(self):
        from ascend.commands.report import _compute_velocity
        today = datetime.now().strftime("%Y-%m-%d")
        snapshots = [{"date": today, "score": 28.0}]
        velocity = _compute_velocity(snapshots)
        assert velocity == 7.0  # 28 / 4 weeks

    def test_compute_momentum(self):
        from ascend.commands.report import _compute_momentum
        today = datetime.now().strftime("%Y-%m-%d")
        snapshots = [{"date": today, "score": 20.0}]
        momentum = _compute_momentum(snapshots)
        assert momentum == 20.0  # 20 recent - 0 prior

    def test_member_status_no_data(self):
        from ascend.commands.report import _member_status
        assert _member_status([], []) == "No Data"

    def test_member_status_pip(self):
        from ascend.commands.report import _member_status
        assert _member_status([], ["pip"]) == "PIP"

    def test_member_status_pto(self):
        from ascend.commands.report import _member_status
        assert _member_status([], ["pto"]) == "PTO"

    def test_member_status_active(self):
        from ascend.commands.report import _member_status
        today = datetime.now().strftime("%Y-%m-%d")
        snapshots = [{"date": today, "score": 20.0}]
        assert _member_status(snapshots, []) == "Active"

    def test_member_status_quiet(self):
        from ascend.commands.report import _member_status
        today = datetime.now().strftime("%Y-%m-%d")
        snapshots = [{"date": today, "score": 2.0}]
        assert _member_status(snapshots, []) == "Quiet"

    def test_date_range_defaults(self):
        from ascend.commands.report import _date_range
        import argparse
        args = argparse.Namespace(days=30, from_date=None, to_date=None)
        from_date, to_date = _date_range(args)
        assert to_date == datetime.now().strftime("%Y-%m-%d")
        expected_from = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        assert from_date == expected_from

    def test_date_range_explicit(self):
        from ascend.commands.report import _date_range
        import argparse
        args = argparse.Namespace(days=30, from_date="2025-01-01", to_date="2025-01-31")
        from_date, to_date = _date_range(args)
        assert from_date == "2025-01-01"
        assert to_date == "2025-01-31"


class TestCLIRewrite:
    """Tests for report command rewriting."""

    def test_rewrite_report_performance(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["report", "performance", "--member", "Alice"]) == \
            ["report-performance", "--member", "Alice"]

    def test_rewrite_report_team(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["report", "team", "--json"]) == ["report-team", "--json"]

    def test_rewrite_report_custom(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["report", "custom", "What risks?"]) == \
            ["report-custom", "What risks?"]
