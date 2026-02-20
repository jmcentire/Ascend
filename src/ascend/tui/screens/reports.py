"""Reports screen — tabbed report views."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import Markdown, Static, TabbedContent, TabPane


class ReportsPanel(Vertical):
    """Report viewer with tabs for different report types."""

    BINDINGS = [
        Binding("r", "regenerate", "Regenerate", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield Static("[b]Reports[/b]", classes="panel-title")
        with TabbedContent("Dashboard", "Team", "Git", "Progress", id="report-tabs"):
            with TabPane("Dashboard", id="tab-dashboard"):
                yield Markdown("*Loading...*", id="report-dashboard")
            with TabPane("Team", id="tab-team"):
                yield Markdown("*Loading...*", id="report-team")
            with TabPane("Git", id="tab-git"):
                yield Markdown("*Loading...*", id="report-git")
            with TabPane("Progress", id="tab-progress"):
                yield Markdown("*Loading...*", id="report-progress")

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        from ascend.config import DB_PATH
        from ascend.db import get_connection

        if not DB_PATH.exists():
            for tab_id in ("report-dashboard", "report-team", "report-git", "report-progress"):
                self.query_one(f"#{tab_id}", Markdown).update("*Run 'ascend init' first*")
            return

        conn = get_connection(DB_PATH)
        try:
            now = datetime.now()
            to_date = now.strftime("%Y-%m-%d")
            from_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")

            self._build_dashboard_report(conn, from_date, to_date)
            self._build_team_report(conn, from_date, to_date)
            self._build_git_report(conn, from_date, to_date)
            self._build_progress_report(conn, from_date, to_date)
        finally:
            conn.close()

    def _build_dashboard_report(self, conn, from_date: str, to_date: str) -> None:
        total_members = conn.execute(
            "SELECT COUNT(*) FROM members WHERE status = 'active'"
        ).fetchone()[0]
        total_teams = conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0]
        meeting_count = conn.execute(
            "SELECT COUNT(*) FROM meetings WHERE date >= ? AND date <= ?",
            (from_date, to_date),
        ).fetchone()[0]
        open_items = conn.execute(
            "SELECT COUNT(*) FROM meeting_items WHERE status = 'open'"
        ).fetchone()[0]

        snapshot_rows = conn.execute(
            """SELECT metrics FROM performance_snapshots
               WHERE date >= ? AND date <= ?""",
            (from_date, to_date),
        ).fetchall()

        total_commits = 0
        total_prs = 0
        total_issues = 0
        for row in snapshot_rows:
            m = json.loads(row["metrics"]) if row["metrics"] else {}
            total_commits += m.get("commits_count", 0)
            total_prs += m.get("prs_merged", 0)
            total_issues += m.get("issues_completed", 0)

        parts = [
            f"# Dashboard — {from_date} to {to_date}\n",
            f"- **Active Members:** {total_members}",
            f"- **Teams:** {total_teams}",
            f"- **Total Commits:** {total_commits}",
            f"- **Total PRs Merged:** {total_prs}",
            f"- **Total Issues Completed:** {total_issues}",
            f"- **Meetings:** {meeting_count}",
            f"- **Open Action Items:** {open_items}",
        ]
        self.query_one("#report-dashboard", Markdown).update("\n".join(parts))

    def _build_team_report(self, conn, from_date: str, to_date: str) -> None:
        members = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM members WHERE status = 'active' ORDER BY name"
            ).fetchall()
        ]

        if not members:
            self.query_one("#report-team", Markdown).update("*No active members*")
            return

        parts = [f"# Team Report — {from_date} to {to_date}\n"]
        parts.append("| Member | Commits | PRs Merged | Issues | Avg Score |")
        parts.append("|--------|---------|------------|--------|-----------|")

        for m in members:
            snapshots = conn.execute(
                """SELECT metrics, score FROM performance_snapshots
                   WHERE member_id = ? AND date >= ? AND date <= ?""",
                (m["id"], from_date, to_date),
            ).fetchall()

            commits = 0
            prs_merged = 0
            issues = 0
            scores = []
            for s in snapshots:
                met = json.loads(s["metrics"]) if s["metrics"] else {}
                commits += met.get("commits_count", 0)
                prs_merged += met.get("prs_merged", 0)
                issues += met.get("issues_completed", 0)
                scores.append(s["score"] or 0)

            avg = round(sum(scores) / len(scores), 1) if scores else 0
            parts.append(
                f"| {m['name']} | {commits} | {prs_merged} | {issues} | {avg} |"
            )

        self.query_one("#report-team", Markdown).update("\n".join(parts))

    def _build_git_report(self, conn, from_date: str, to_date: str) -> None:
        members = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM members WHERE status = 'active' AND github IS NOT NULL ORDER BY name"
            ).fetchall()
        ]

        if not members:
            self.query_one("#report-git", Markdown).update("*No members with GitHub handles*")
            return

        parts = [f"# Git Report — {from_date} to {to_date}\n"]
        parts.append("| Member | GitHub | Commits | PRs Opened | PRs Merged |")
        parts.append("|--------|--------|---------|------------|------------|")

        for m in members:
            snapshots = conn.execute(
                """SELECT metrics FROM performance_snapshots
                   WHERE member_id = ? AND date >= ? AND date <= ?""",
                (m["id"], from_date, to_date),
            ).fetchall()

            commits = 0
            prs_opened = 0
            prs_merged = 0
            for s in snapshots:
                met = json.loads(s["metrics"]) if s["metrics"] else {}
                commits += met.get("commits_count", 0)
                prs_opened += met.get("prs_opened", 0)
                prs_merged += met.get("prs_merged", 0)

            parts.append(
                f"| {m['name']} | @{m['github']} | {commits} | {prs_opened} | {prs_merged} |"
            )

        self.query_one("#report-git", Markdown).update("\n".join(parts))

    def _build_progress_report(self, conn, from_date: str, to_date: str) -> None:
        daily: dict[str, dict] = defaultdict(lambda: {"total": 0.0, "count": 0})

        rows = conn.execute(
            """SELECT date, score FROM performance_snapshots
               WHERE date >= ? AND date <= ?
               ORDER BY date""",
            (from_date, to_date),
        ).fetchall()

        for r in rows:
            d = daily[r["date"]]
            d["total"] += r["score"] or 0
            d["count"] += 1

        if not daily:
            self.query_one("#report-progress", Markdown).update("*No snapshot data*")
            return

        parts = [f"# Progress — {from_date} to {to_date}\n"]
        parts.append(f"**Days with data:** {len(daily)}\n")
        parts.append("| Date | Avg Score | Snapshots |")
        parts.append("|------|-----------|-----------|")

        for date in sorted(daily.keys()):
            d = daily[date]
            avg = round(d["total"] / d["count"], 1) if d["count"] else 0
            parts.append(f"| {date} | {avg} | {d['count']} |")

        self.query_one("#report-progress", Markdown).update("\n".join(parts))

    def action_regenerate(self) -> None:
        self.refresh_data()
        self.app.notify("Reports regenerated")
