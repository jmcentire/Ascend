"""Tests for Phase 6 — Scheduling."""

import json
from datetime import datetime, timedelta
from io import StringIO
from unittest.mock import patch

import pytest

from ascend.cli import main


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
    monkeypatch.setattr("ascend.commands.plan.DB_PATH", home / "ascend.db")
    monkeypatch.setattr("ascend.commands.coach.DB_PATH", home / "ascend.db")
    monkeypatch.setattr("ascend.commands.schedule.DB_PATH", home / "ascend.db")
    monkeypatch.setattr("ascend.commands.schedule.SCHEDULES_DIR", home / "schedules")
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


def _init():
    _capture(["init"])


# ---- Scheduler Module Unit Tests ----

class TestSchedulerCron:
    """Unit tests for cron expression generation."""

    def test_daily(self):
        from ascend.scheduler import schedule_to_cron
        assert schedule_to_cron(daily=True) == "0 9 * * *"

    def test_weekdays(self):
        from ascend.scheduler import schedule_to_cron
        assert schedule_to_cron(weekdays=True) == "0 9 * * 1-5"

    def test_weekly_tuesday(self):
        from ascend.scheduler import schedule_to_cron
        assert schedule_to_cron(weekly="tuesday") == "0 9 * * 2"

    def test_weekly_friday(self):
        from ascend.scheduler import schedule_to_cron
        assert schedule_to_cron(weekly="Friday") == "0 9 * * 5"

    def test_biweekly(self):
        from ascend.scheduler import schedule_to_cron
        cron = schedule_to_cron(biweekly="thursday")
        assert "4" in cron  # Thursday = 4
        assert "8-14,22-28" in cron

    def test_monthly(self):
        from ascend.scheduler import schedule_to_cron
        assert schedule_to_cron(monthly="1,15") == "0 9 1,15 * *"

    def test_quarterly(self):
        from ascend.scheduler import schedule_to_cron
        assert schedule_to_cron(quarterly=True) == "0 9 1 1,4,7,10 *"

    def test_custom_time(self):
        from ascend.scheduler import schedule_to_cron
        assert schedule_to_cron(daily=True, hour=14, minute=30) == "30 14 * * *"

    def test_unknown_day(self):
        from ascend.scheduler import schedule_to_cron
        with pytest.raises(ValueError):
            schedule_to_cron(weekly="notaday")

    def test_no_frequency(self):
        from ascend.scheduler import schedule_to_cron
        with pytest.raises(ValueError):
            schedule_to_cron()


class TestCronParsing:
    """Unit tests for cron parsing and next-run computation."""

    def test_parse_cron(self):
        from ascend.scheduler import parse_cron
        result = parse_cron("0 9 * * *")
        assert result["minute"] == "0"
        assert result["hour"] == "9"
        assert result["dom"] == "*"
        assert result["month"] == "*"
        assert result["dow"] == "*"

    def test_parse_cron_invalid(self):
        from ascend.scheduler import parse_cron
        with pytest.raises(ValueError):
            parse_cron("bad")

    def test_compute_next_run_daily(self):
        from ascend.scheduler import compute_next_run
        # After 8:00am, next daily at 9:00 should be today at 9:00 (or tomorrow)
        after = datetime(2025, 6, 15, 8, 0)
        result = compute_next_run("0 9 * * *", after=after)
        assert result == "2025-06-15 09:00"

    def test_compute_next_run_daily_after(self):
        from ascend.scheduler import compute_next_run
        # After 10:00am, next daily at 9:00 should be tomorrow
        after = datetime(2025, 6, 15, 10, 0)
        result = compute_next_run("0 9 * * *", after=after)
        assert result == "2025-06-16 09:00"

    def test_compute_next_run_weekly(self):
        from ascend.scheduler import compute_next_run
        # 2025-06-15 is a Sunday. Weekly on Tuesday (2) should be 2025-06-17
        after = datetime(2025, 6, 15, 10, 0)
        result = compute_next_run("0 9 * * 2", after=after)
        assert result == "2025-06-17 09:00"

    def test_compute_next_run_monthly(self):
        from ascend.scheduler import compute_next_run
        after = datetime(2025, 6, 10, 10, 0)
        result = compute_next_run("0 9 15 * *", after=after)
        assert result == "2025-06-15 09:00"

    def test_compute_next_run_quarterly(self):
        from ascend.scheduler import compute_next_run
        after = datetime(2025, 6, 15, 10, 0)
        result = compute_next_run("0 9 1 1,4,7,10 *", after=after)
        assert result == "2025-07-01 09:00"

    def test_expand_field_star(self):
        from ascend.scheduler import _expand_field
        result = _expand_field("*", 0, 6)
        assert result == {0, 1, 2, 3, 4, 5, 6}

    def test_expand_field_range(self):
        from ascend.scheduler import _expand_field
        result = _expand_field("1-5", 0, 6)
        assert result == {1, 2, 3, 4, 5}

    def test_expand_field_list(self):
        from ascend.scheduler import _expand_field
        result = _expand_field("1,4,7,10", 1, 12)
        assert result == {1, 4, 7, 10}


class TestCronDescription:
    """Unit tests for human-readable cron descriptions."""

    def test_daily(self):
        from ascend.scheduler import describe_cron
        assert describe_cron("0 9 * * *") == "daily at 09:00"

    def test_weekdays(self):
        from ascend.scheduler import describe_cron
        assert describe_cron("0 9 * * 1-5") == "weekdays at 09:00"

    def test_weekly(self):
        from ascend.scheduler import describe_cron
        desc = describe_cron("0 9 * * 2")
        assert "Tue" in desc
        assert "09:00" in desc

    def test_monthly(self):
        from ascend.scheduler import describe_cron
        desc = describe_cron("0 9 1,15 * *")
        assert "monthly" in desc
        assert "1,15" in desc


class TestPlistGeneration:
    """Unit tests for launchd plist generation."""

    def test_cron_to_calendar_intervals_daily(self):
        from ascend.scheduler import _cron_to_calendar_intervals
        xml = _cron_to_calendar_intervals("0 9 * * *")
        assert "<key>Hour</key>" in xml
        assert "<integer>9</integer>" in xml

    def test_cron_to_calendar_intervals_weekdays(self):
        from ascend.scheduler import _cron_to_calendar_intervals
        xml = _cron_to_calendar_intervals("0 9 * * 1-5")
        assert "<key>Weekday</key>" in xml
        # Should have 5 entries (Mon-Fri)
        assert xml.count("<key>Weekday</key>") == 5

    def test_write_plist(self, tmp_path, monkeypatch):
        from ascend.scheduler import write_plist
        # Override home to temp dir
        fake_home = tmp_path / "fakehome"
        fake_home.mkdir()
        monkeypatch.setattr("ascend.scheduler.Path.home", lambda: fake_home)
        schedules_dir = tmp_path / "schedules"
        schedules_dir.mkdir()
        path = write_plist("test-schedule", "0 9 * * *", schedules_dir)
        assert path.exists()
        content = path.read_text()
        assert "com.ascend.schedule.test-schedule" in content
        assert "schedule" in content
        assert "run" in content


# ---- Schedule CLI Tests ----

class TestScheduleList:
    def test_list_empty(self, isolated_home):
        _init()
        data = _capture_json(["schedule", "list"])
        assert data == []

    def test_list_text_empty(self, isolated_home):
        _init()
        output = _capture(["schedule", "list"])
        assert "No schedules" in output


class TestScheduleAdd:
    def test_add_daily(self, isolated_home):
        _init()
        with patch("ascend.commands.schedule.write_plist", return_value=None):
            data = _capture_json([
                "schedule", "add", "daily-sync", "sync snapshot", "--daily", "--no-launchd",
            ])
        assert data["name"] == "daily-sync"
        assert data["command"] == "sync snapshot"
        assert data["cron_expr"] == "0 9 * * *"
        assert data["enabled"] is True

    def test_add_weekdays(self, isolated_home):
        _init()
        data = _capture_json([
            "schedule", "add", "weekday-sync", "sync", "--weekdays", "--no-launchd",
        ])
        assert data["cron_expr"] == "0 9 * * 1-5"

    def test_add_weekly(self, isolated_home):
        _init()
        data = _capture_json([
            "schedule", "add", "weekly-report", "report team --copy", "--weekly", "tuesday",
            "--no-launchd",
        ])
        assert data["cron_expr"] == "0 9 * * 2"
        assert "Tue" in data["description"]

    def test_add_monthly(self, isolated_home):
        _init()
        data = _capture_json([
            "schedule", "add", "monthly-review", "report dashboard", "--monthly", "1,15",
            "--no-launchd",
        ])
        assert data["cron_expr"] == "0 9 1,15 * *"

    def test_add_quarterly(self, isolated_home):
        _init()
        data = _capture_json([
            "schedule", "add", "quarterly-review", "report performance", "--quarterly",
            "--no-launchd",
        ])
        assert "1,4,7,10" in data["cron_expr"]

    def test_add_duplicate(self, isolated_home):
        _init()
        _capture(["schedule", "add", "test", "sync", "--daily", "--no-launchd"])
        data = _capture_json(["schedule", "add", "test", "sync", "--daily", "--no-launchd"])
        assert "error" in data

    def test_add_shows_in_list(self, isolated_home):
        _init()
        _capture(["schedule", "add", "my-sched", "sync snapshot", "--daily", "--no-launchd"])
        data = _capture_json(["schedule", "list"])
        assert len(data) == 1
        assert data[0]["name"] == "my-sched"

    def test_add_text_output(self, isolated_home):
        _init()
        output = _capture([
            "schedule", "add", "test-sched", "sync", "--daily", "--no-launchd",
        ])
        assert "test-sched" in output
        assert "created" in output


class TestScheduleRemove:
    def test_remove(self, isolated_home):
        _init()
        _capture(["schedule", "add", "to-remove", "sync", "--daily", "--no-launchd"])
        with patch("ascend.commands.schedule.remove_plist"):
            data = _capture_json(["schedule", "remove", "to-remove"])
        assert data["removed"] == "to-remove"
        # Verify gone
        listed = _capture_json(["schedule", "list"])
        assert len(listed) == 0

    def test_remove_not_found(self, isolated_home):
        _init()
        data = _capture_json(["schedule", "remove", "nonexistent"])
        assert "error" in data

    def test_remove_text(self, isolated_home):
        _init()
        _capture(["schedule", "add", "rm-me", "sync", "--daily", "--no-launchd"])
        with patch("ascend.commands.schedule.remove_plist"):
            output = _capture(["schedule", "remove", "rm-me"])
        assert "removed" in output


class TestScheduleRun:
    def test_run_executes_command(self, isolated_home):
        _init()
        _capture(["roster", "add", "Alice", "--github", "alice"])
        _capture(["schedule", "add", "test-run", "roster list --json", "--daily", "--no-launchd"])
        # Run the schedule — it should execute "roster list --json"
        data = _capture_json(["schedule", "run", "test-run"])
        assert data["name"] == "test-run"
        assert data["error"] is None
        assert data["ran_at"] is not None
        assert data["next_run"] is not None

    def test_run_updates_timestamps(self, isolated_home):
        _init()
        _capture(["schedule", "add", "ts-test", "config show", "--daily", "--no-launchd"])
        _capture(["schedule", "run", "ts-test"])
        data = _capture_json(["schedule", "list"])
        sched = data[0]
        assert sched["last_run"] is not None

    def test_run_not_found(self, isolated_home):
        _init()
        data = _capture_json(["schedule", "run", "nonexistent"])
        assert "error" in data


class TestScheduleEnableDisable:
    def test_disable(self, isolated_home):
        _init()
        _capture(["schedule", "add", "toggle-me", "sync", "--daily", "--no-launchd"])
        data = _capture_json(["schedule", "disable", "toggle-me"])
        assert data["enabled"] is False
        listed = _capture_json(["schedule", "list"])
        assert listed[0]["enabled"] == 0

    def test_enable(self, isolated_home):
        _init()
        _capture(["schedule", "add", "toggle-me", "sync", "--daily", "--no-launchd"])
        _capture(["schedule", "disable", "toggle-me"])
        data = _capture_json(["schedule", "enable", "toggle-me"])
        assert data["enabled"] is True
        assert data["next_run"] is not None

    def test_enable_not_found(self, isolated_home):
        _init()
        data = _capture_json(["schedule", "enable", "nonexistent"])
        assert "error" in data

    def test_disable_not_found(self, isolated_home):
        _init()
        data = _capture_json(["schedule", "disable", "nonexistent"])
        assert "error" in data

    def test_disable_text(self, isolated_home):
        _init()
        _capture(["schedule", "add", "txt-test", "sync", "--daily", "--no-launchd"])
        output = _capture(["schedule", "disable", "txt-test"])
        assert "disabled" in output

    def test_enable_text(self, isolated_home):
        _init()
        _capture(["schedule", "add", "txt-test", "sync", "--daily", "--no-launchd"])
        _capture(["schedule", "disable", "txt-test"])
        output = _capture(["schedule", "enable", "txt-test"])
        assert "enabled" in output


# ---- CLI Rewrite ----

class TestCLIRewritePhase6:
    def test_rewrite_schedule_list(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["schedule", "list"]) == ["schedule-list"]

    def test_rewrite_schedule_add(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["schedule", "add", "name", "cmd", "--daily"]) == \
            ["schedule-add", "name", "cmd", "--daily"]

    def test_rewrite_schedule_remove(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["schedule", "remove", "name"]) == ["schedule-remove", "name"]

    def test_rewrite_schedule_run(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["schedule", "run", "name"]) == ["schedule-run", "name"]

    def test_rewrite_schedule_enable(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["schedule", "enable", "name"]) == ["schedule-enable", "name"]

    def test_rewrite_schedule_disable(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["schedule", "disable", "name"]) == ["schedule-disable", "name"]
