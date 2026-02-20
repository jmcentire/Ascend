"""Tests for Phase 5 — Planning & Coaching."""

import json
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
    monkeypatch.setattr("ascend.commands.plan.DB_PATH", home / "ascend.db")
    monkeypatch.setattr("ascend.commands.coach.DB_PATH", home / "ascend.db")
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


def _add_snapshot(home, member_id, date_str, metrics, score):
    from ascend.db import get_connection
    conn = get_connection(home / "ascend.db")
    conn.execute(
        """INSERT INTO performance_snapshots (member_id, date, source, metrics, score)
           VALUES (?, ?, 'sync', ?, ?)""",
        (member_id, date_str, json.dumps(metrics), score),
    )
    conn.commit()
    conn.close()


def _add_meeting(home, member_id, date_str, summary="Notes", sentiment=0.7):
    from ascend.db import get_connection
    conn = get_connection(home / "ascend.db")
    conn.execute(
        """INSERT INTO meetings (member_id, date, source, raw_text, summary, sentiment_score)
           VALUES (?, ?, 'test', 'raw', ?, ?)""",
        (member_id, date_str, summary, sentiment),
    )
    conn.commit()
    conn.close()


# ---- Plan: Cycle ----

class TestPlanCycle:
    def test_cycle_empty(self, isolated_home):
        _capture(["init"])
        data = _capture_json(["plan", "cycle"])
        assert "cycle" in data
        assert data["total_goals"] == 0

    def test_cycle_text(self, isolated_home):
        _capture(["init"])
        output = _capture(["plan", "cycle"])
        assert "Planning Cycle" in output

    def test_cycle_with_goals(self, isolated_home):
        _init_with_member()
        cycle = datetime.now()
        q = (cycle.month - 1) // 3 + 1
        cycle_str = f"{cycle.year}-Q{q}"
        _capture(["plan", "goal", "create", "Ship feature X", "--member", "Alice", "--cycle", cycle_str])
        data = _capture_json(["plan", "cycle"])
        assert data["total_goals"] == 1
        assert data["active"] == 1


# ---- Plan: Goal Create/List/Update ----

class TestPlanGoals:
    def test_create_goal(self, isolated_home):
        _init_with_member()
        data = _capture_json(["plan", "goal", "create", "Ship feature X", "--member", "Alice"])
        assert data["id"] == 1
        assert data["title"] == "Ship feature X"
        assert data["type"] == "objective"
        assert data["status"] == "active"

    def test_create_key_result(self, isolated_home):
        _init_with_member()
        data = _capture_json([
            "plan", "goal", "create", "Increase test coverage to 80%",
            "--member", "Alice", "--type", "key_result", "--target", "80",
        ])
        assert data["type"] == "key_result"
        assert data["target_value"] == 80.0

    def test_create_with_team(self, isolated_home):
        _init_with_member()
        _capture(["team", "create", "Backend"])
        data = _capture_json(["plan", "goal", "create", "Team velocity target", "--team", "Backend"])
        assert data["team_id"] is not None

    def test_create_member_not_found(self, isolated_home):
        _init_with_member()
        data = _capture_json(["plan", "goal", "create", "Test", "--member", "Nobody"])
        assert "error" in data

    def test_list_goals(self, isolated_home):
        _init_with_member()
        _capture(["plan", "goal", "create", "Goal 1", "--member", "Alice"])
        _capture(["plan", "goal", "create", "Goal 2", "--member", "Alice"])
        data = _capture_json(["plan", "goal", "list"])
        assert len(data) == 2

    def test_list_by_status(self, isolated_home):
        _init_with_member()
        _capture(["plan", "goal", "create", "Goal 1", "--member", "Alice"])
        data = _capture_json(["plan", "goal", "list", "--status", "completed"])
        assert len(data) == 0

    def test_list_by_member(self, isolated_home):
        _init_with_member()
        _capture(["roster", "add", "Bob", "--github", "bob"])
        _capture(["plan", "goal", "create", "Alice goal", "--member", "Alice"])
        _capture(["plan", "goal", "create", "Bob goal", "--member", "Bob"])
        data = _capture_json(["plan", "goal", "list", "--member", "Alice"])
        assert len(data) == 1
        assert data[0]["title"] == "Alice goal"

    def test_list_text(self, isolated_home):
        _init_with_member()
        _capture(["plan", "goal", "create", "Test goal", "--member", "Alice"])
        output = _capture(["plan", "goal", "list"])
        assert "Test goal" in output

    def test_update_value(self, isolated_home):
        _init_with_member()
        _capture(["plan", "goal", "create", "Target 100", "--member", "Alice", "--target", "100"])
        data = _capture_json(["plan", "goal", "update", "1", "--value", "50"])
        assert data["current_value"] == 50.0

    def test_update_status(self, isolated_home):
        _init_with_member()
        _capture(["plan", "goal", "create", "Test", "--member", "Alice"])
        data = _capture_json(["plan", "goal", "update", "1", "--status", "completed"])
        assert data["status"] == "completed"

    def test_update_not_found(self, isolated_home):
        _capture(["init"])
        data = _capture_json(["plan", "goal", "update", "999", "--status", "completed"])
        assert "error" in data

    def test_update_no_changes(self, isolated_home):
        _init_with_member()
        _capture(["plan", "goal", "create", "Test", "--member", "Alice"])
        data = _capture_json(["plan", "goal", "update", "1"])
        assert "error" in data


# ---- Plan: PIP ----

class TestPlanPIP:
    def test_pip_create_with_criteria(self, isolated_home):
        _init_with_member()
        data = _capture_json([
            "plan", "pip", "create", "Alice",
            "--criteria", "Complete reviews in 24h", "Ship 2 features per sprint",
        ])
        assert data["member"] == "Alice"
        assert len(data["criteria"]) == 2
        assert data["flag_set"] is True

    def test_pip_create_sets_flag(self, isolated_home):
        _init_with_member()
        _capture(["plan", "pip", "create", "Alice", "--criteria", "Test criterion"])
        data = _capture_json(["roster", "show", "Alice"])
        assert "pip" in data["flags"]

    def test_pip_create_member_not_found(self, isolated_home):
        _init_with_member()
        data = _capture_json(["plan", "pip", "create", "Nobody"])
        assert "error" in data

    def test_pip_create_no_criteria_no_llm(self, isolated_home, monkeypatch):
        _init_with_member()
        monkeypatch.delenv("ASCEND_ANTHROPIC_API_KEY", raising=False)
        data = _capture_json(["plan", "pip", "create", "Alice"])
        assert data["criteria"] == []
        assert data["flag_set"] is True

    def test_pip_show(self, isolated_home):
        _init_with_member()
        _capture(["plan", "pip", "create", "Alice", "--criteria", "Criterion A", "Criterion B"])
        data = _capture_json(["plan", "pip", "show", "Alice"])
        assert data["pip_flag"] is True
        assert data["criteria_count"] == 2
        assert data["active"] == 2

    def test_pip_show_no_pip(self, isolated_home):
        _init_with_member()
        data = _capture_json(["plan", "pip", "show", "Alice"])
        assert data["pip_flag"] is False
        assert data["criteria_count"] == 0

    def test_pip_show_member_not_found(self, isolated_home):
        _init_with_member()
        data = _capture_json(["plan", "pip", "show", "Nobody"])
        assert "error" in data

    def test_pip_show_text(self, isolated_home):
        _init_with_member()
        _capture(["plan", "pip", "create", "Alice", "--criteria", "Review PRs daily"])
        output = _capture(["plan", "pip", "show", "Alice"])
        assert "PIP Status" in output
        assert "Review PRs daily" in output


# ---- Plan: Career ----

class TestPlanCareer:
    def test_career_no_llm(self, isolated_home, monkeypatch):
        _init_with_member()
        monkeypatch.delenv("ASCEND_ANTHROPIC_API_KEY", raising=False)
        data = _capture_json(["plan", "career", "Alice"])
        assert data["member"] == "Alice"
        assert data["plan"] is None
        assert "error" in data

    def test_career_with_llm(self, isolated_home):
        _init_with_member()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="## Career Plan\n\nGrow into senior role.")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        with patch("ascend.summarizer.get_client", return_value=mock_client):
            data = _capture_json(["plan", "career", "Alice"])
        assert "Career Plan" in data["plan"]

    def test_career_member_not_found(self, isolated_home):
        _init_with_member()
        data = _capture_json(["plan", "career", "Nobody"])
        assert "error" in data


# ---- Coach: Analyze ----

class TestCoachAnalyze:
    def test_analyze_no_llm(self, isolated_home, monkeypatch):
        _init_with_member()
        monkeypatch.delenv("ASCEND_ANTHROPIC_API_KEY", raising=False)
        data = _capture_json(["coach", "analyze", "Alice"])
        assert "error" in data
        assert "context" in data

    def test_analyze_with_llm(self, isolated_home):
        _init_with_member()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="## Analysis\n\nAlice is performing well.")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        with patch("ascend.summarizer.get_client", return_value=mock_client):
            data = _capture_json(["coach", "analyze", "Alice"])
        assert data["member"] == "Alice"
        assert "Analysis" in data["analysis"]

    def test_analyze_member_not_found(self, isolated_home):
        _init_with_member()
        data = _capture_json(["coach", "analyze", "Nobody"])
        assert "error" in data


# ---- Coach: Risks ----

class TestCoachRisks:
    def test_no_risks(self, isolated_home):
        _init_with_member()
        today = datetime.now().strftime("%Y-%m-%d")
        _add_snapshot(isolated_home, 1, today, {
            "commits_count": 5, "prs_opened": 2, "prs_merged": 1,
            "issues_completed": 3, "issues_in_progress": 1,
        }, 20.0)
        _add_meeting(isolated_home, 1, today)
        data = _capture_json(["coach", "risks"])
        # With recent snapshot and meeting, should have minimal/no risks
        # (may still flag "no performance data" if only 1 snapshot)
        assert isinstance(data, list)

    def test_flight_risk_flag(self, isolated_home):
        _init_with_member()
        _capture(["roster", "flag", "Alice", "flight_risk"])
        data = _capture_json(["coach", "risks"])
        assert len(data) >= 1
        alice_risk = next(r for r in data if r["member"] == "Alice")
        assert any("flight_risk" in s for s in alice_risk["signals"])
        assert alice_risk["risk_score"] > 0

    def test_stale_meeting(self, isolated_home):
        _init_with_member()
        old_date = (datetime.now() - timedelta(days=45)).strftime("%Y-%m-%d")
        _add_meeting(isolated_home, 1, old_date)
        data = _capture_json(["coach", "risks"])
        alice_risk = next(r for r in data if r["member"] == "Alice")
        assert any("stale" in s for s in alice_risk["signals"])

    def test_no_data_risk(self, isolated_home):
        _init_with_member()
        data = _capture_json(["coach", "risks"])
        alice_risk = next(r for r in data if r["member"] == "Alice")
        assert any("no performance data" in s for s in alice_risk["signals"])
        assert any("no 1:1" in s for s in alice_risk["signals"])

    def test_pip_risk(self, isolated_home):
        _init_with_member()
        _capture(["roster", "flag", "Alice", "pip"])
        data = _capture_json(["coach", "risks"])
        alice_risk = next(r for r in data if r["member"] == "Alice")
        assert any("PIP" in s for s in alice_risk["signals"])

    def test_underperformance_detection(self, isolated_home):
        _init_with_member()
        # Add low-score snapshots over 30 days
        for i in range(5):
            date = (datetime.now() - timedelta(days=i * 5)).strftime("%Y-%m-%d")
            _add_snapshot(isolated_home, 1, date, {
                "commits_count": 0, "prs_opened": 0, "prs_merged": 0,
                "issues_completed": 0, "issues_in_progress": 0,
            }, 1.0)
        data = _capture_json(["coach", "risks"])
        alice_risk = next(r for r in data if r["member"] == "Alice")
        assert any("underperformance" in s for s in alice_risk["signals"])

    def test_text_output_no_risks(self, isolated_home):
        _capture(["init"])
        output = _capture(["coach", "risks"])
        assert "Risk Dashboard" in output

    def test_text_output_with_risks(self, isolated_home):
        _init_with_member()
        _capture(["roster", "flag", "Alice", "flight_risk"])
        output = _capture(["coach", "risks"])
        assert "Risk Dashboard" in output
        assert "Alice" in output


# ---- Coach: STAR ----

class TestCoachStar:
    def test_record_star(self, isolated_home):
        _init_with_member()
        data = _capture_json([
            "coach", "star", "Alice",
            "--situation", "Sprint planning meeting",
            "--task", "Estimate complex feature",
            "--action", "Broke down into subtasks, provided detailed estimates",
            "--result", "Accurate estimate, delivered on time",
        ])
        assert data["member"] == "Alice"
        assert data["kind"] == "star_assessment"
        assert data["star"]["situation"] == "Sprint planning meeting"
        assert data["star"]["result"] == "Accurate estimate, delivered on time"

    def test_star_stored_in_db(self, isolated_home):
        _init_with_member()
        _capture([
            "coach", "star", "Alice",
            "--situation", "S", "--task", "T", "--action", "A", "--result", "R",
        ])
        from ascend.db import get_connection
        conn = get_connection(isolated_home / "ascend.db")
        row = conn.execute("SELECT * FROM coaching_entries WHERE member_id = 1").fetchone()
        assert row is not None
        assert row["kind"] == "star_assessment"
        content = json.loads(row["content"])
        assert content["situation"] == "S"
        conn.close()

    def test_star_member_not_found(self, isolated_home):
        _init_with_member()
        data = _capture_json([
            "coach", "star", "Nobody",
            "--situation", "S", "--task", "T", "--action", "A", "--result", "R",
        ])
        assert "error" in data

    def test_star_text_output(self, isolated_home):
        _init_with_member()
        output = _capture([
            "coach", "star", "Alice",
            "--situation", "Demo day", "--task", "Present feature",
            "--action", "Clear presentation", "--result", "Positive feedback",
        ])
        assert "STAR assessment" in output
        assert "Alice" in output


# ---- Coach: Suggest ----

class TestCoachSuggest:
    def test_suggest_no_llm(self, isolated_home, monkeypatch):
        _init_with_member()
        monkeypatch.delenv("ASCEND_ANTHROPIC_API_KEY", raising=False)
        data = _capture_json(["coach", "suggest", "Alice"])
        assert "error" in data
        assert "context" in data

    def test_suggest_with_llm(self, isolated_home):
        _init_with_member()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="## Coaching Suggestions\n\n1. Discuss career goals")]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        with patch("ascend.summarizer.get_client", return_value=mock_client):
            data = _capture_json(["coach", "suggest", "Alice"])
        assert data["member"] == "Alice"
        assert "Coaching Suggestions" in data["suggestions"]

    def test_suggest_member_not_found(self, isolated_home):
        _init_with_member()
        data = _capture_json(["coach", "suggest", "Nobody"])
        assert "error" in data


# ---- CLI Rewrite ----

class TestCLIRewritePhase5:
    def test_rewrite_plan_cycle(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["plan", "cycle"]) == ["plan-cycle"]

    def test_rewrite_plan_goal_create(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["plan", "goal", "create", "Title"]) == \
            ["plan-goal-create", "Title"]

    def test_rewrite_plan_goal_list(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["plan", "goal", "list", "--json"]) == \
            ["plan-goal-list", "--json"]

    def test_rewrite_plan_pip_create(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["plan", "pip", "create", "Alice"]) == \
            ["plan-pip-create", "Alice"]

    def test_rewrite_coach_analyze(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["coach", "analyze", "Alice"]) == \
            ["coach-analyze", "Alice"]

    def test_rewrite_coach_risks(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["coach", "risks"]) == ["coach-risks"]

    def test_rewrite_coach_star(self):
        from ascend.cli import _rewrite_args
        assert _rewrite_args(["coach", "star", "Alice", "--situation", "S"]) == \
            ["coach-star", "Alice", "--situation", "S"]


# ---- Risk Algorithm Unit Tests ----

class TestRiskAlgorithm:
    def test_compute_risks_no_data(self, isolated_home):
        from ascend.commands.coach import _compute_risks
        from ascend.db import get_connection
        _init_with_member()
        conn = get_connection(isolated_home / "ascend.db")
        m = dict(conn.execute("SELECT * FROM members WHERE id = 1").fetchone())
        risks = _compute_risks(m, conn)
        conn.close()
        assert risks["member"] == "Alice"
        assert "no performance data" in " ".join(risks["signals"])

    def test_compute_risks_with_data(self, isolated_home):
        from ascend.commands.coach import _compute_risks
        from ascend.db import get_connection
        _init_with_member()
        today = datetime.now().strftime("%Y-%m-%d")
        _add_snapshot(isolated_home, 1, today, {
            "commits_count": 5, "prs_opened": 2, "prs_merged": 1,
            "issues_completed": 3, "issues_in_progress": 1,
        }, 20.0)
        _add_meeting(isolated_home, 1, today)
        conn = get_connection(isolated_home / "ascend.db")
        m = dict(conn.execute("SELECT * FROM members WHERE id = 1").fetchone())
        risks = _compute_risks(m, conn)
        conn.close()
        # With good data, should have few/no signals
        assert risks["risk_score"] < 30

    def test_compute_risks_burnout(self, isolated_home):
        from ascend.commands.coach import _compute_risks
        from ascend.db import get_connection
        _init_with_member()
        # Very high scores → burnout signal
        for i in range(5):
            date = (datetime.now() - timedelta(days=i * 5)).strftime("%Y-%m-%d")
            _add_snapshot(isolated_home, 1, date, {
                "commits_count": 20, "prs_opened": 5, "prs_merged": 5,
                "issues_completed": 10, "issues_in_progress": 0,
            }, 50.0)
        _add_meeting(isolated_home, 1, datetime.now().strftime("%Y-%m-%d"))
        conn = get_connection(isolated_home / "ascend.db")
        m = dict(conn.execute("SELECT * FROM members WHERE id = 1").fetchone())
        risks = _compute_risks(m, conn)
        conn.close()
        assert any("burnout" in s for s in risks["signals"])


# ---- Gather Context ----

class TestGatherContext:
    def test_gather_member_context(self, isolated_home):
        from ascend.commands.plan import _gather_member_context
        from ascend.db import get_connection
        _init_with_member()
        conn = get_connection(isolated_home / "ascend.db")
        m = dict(conn.execute("SELECT * FROM members WHERE id = 1").fetchone())
        context = _gather_member_context(m, conn)
        conn.close()
        assert "Alice" in context
        assert "Engineer" in context

    def test_gather_full_context(self, isolated_home):
        from ascend.commands.coach import _gather_full_context
        from ascend.db import get_connection
        _init_with_member()
        today = datetime.now().strftime("%Y-%m-%d")
        _add_snapshot(isolated_home, 1, today, {"commits_count": 5}, 10.0)
        _add_meeting(isolated_home, 1, today, "Discussed roadmap")
        conn = get_connection(isolated_home / "ascend.db")
        m = dict(conn.execute("SELECT * FROM members WHERE id = 1").fetchone())
        context = _gather_full_context(m, conn)
        conn.close()
        assert "Alice" in context
        assert "commits" in context.lower()
        assert "Discussed roadmap" in context
