"""Dashboard screen — org overview, risk alerts, schedules, recent meetings."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer
from textual.widgets import DataTable, Static


class DashboardPanel(ScrollableContainer):
    """Dashboard showing org overview."""

    def compose(self) -> ComposeResult:
        yield Static("[b]Dashboard[/b]", classes="panel-title")
        with Horizontal(classes="stats-row"):
            yield Static("", id="stat-members", classes="stat-card")
            yield Static("", id="stat-flags", classes="stat-card")
            yield Static("", id="stat-meetings", classes="stat-card")
            yield Static("", id="stat-items", classes="stat-card")
        yield Static("[b]Risk Alerts[/b]", classes="section-title")
        yield DataTable(id="risk-table", classes="dashboard-table")
        yield Static("[b]Upcoming Schedules[/b]", classes="section-title")
        yield DataTable(id="schedule-table", classes="dashboard-table")
        yield Static("[b]Recent Meetings (7 days)[/b]", classes="section-title")
        yield DataTable(id="recent-meetings-table", classes="dashboard-table")

    def on_mount(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        from ascend.config import DB_PATH
        from ascend.db import get_connection

        if not DB_PATH.exists():
            self.query_one("#stat-members", Static).update(
                "[yellow]Run 'ascend init' first[/]"
            )
            return

        conn = get_connection(DB_PATH)
        try:
            self._load_stats(conn)
            self._load_risks(conn)
            self._load_schedules(conn)
            self._load_meetings(conn)
        finally:
            conn.close()

    def _load_stats(self, conn) -> None:
        members = conn.execute(
            "SELECT COUNT(*) FROM members WHERE status = 'active'"
        ).fetchone()[0]
        pip = conn.execute(
            "SELECT COUNT(DISTINCT member_id) FROM member_flags WHERE flag = 'pip'"
        ).fetchone()[0]
        pto = conn.execute(
            "SELECT COUNT(DISTINCT member_id) FROM member_flags WHERE flag = 'pto'"
        ).fetchone()[0]
        oncall = conn.execute(
            "SELECT COUNT(DISTINCT member_id) FROM member_flags WHERE flag = 'oncall'"
        ).fetchone()[0]
        meetings = conn.execute("SELECT COUNT(*) FROM meetings").fetchone()[0]
        items = conn.execute(
            "SELECT COUNT(*) FROM meeting_items WHERE status = 'open'"
        ).fetchone()[0]

        self.query_one("#stat-members", Static).update(f"[b]{members}[/]\nMembers")
        self.query_one("#stat-flags", Static).update(
            f"[b]{pip}[/] PIP  [b]{pto}[/] PTO  [b]{oncall}[/] OnCall"
        )
        self.query_one("#stat-meetings", Static).update(f"[b]{meetings}[/]\nMeetings")
        self.query_one("#stat-items", Static).update(f"[b]{items}[/]\nOpen Items")

    def _load_risks(self, conn) -> None:
        from ascend.commands.coach import _compute_risks

        table = self.query_one("#risk-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Member", "Score", "Top Signal")
        table.cursor_type = "row"

        members = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM members WHERE status = 'active'"
            ).fetchall()
        ]

        risks = []
        for m in members:
            r = _compute_risks(m, conn)
            if r["signals"]:
                risks.append(r)
        risks.sort(key=lambda x: x["risk_score"], reverse=True)

        for r in risks[:5]:
            top = r["signals"][0] if r["signals"] else ""
            table.add_row(r["member"], str(r["risk_score"]), top)

        if not risks:
            table.add_row("—", "—", "No risk signals detected")

    def _load_schedules(self, conn) -> None:
        table = self.query_one("#schedule-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Name", "Schedule", "Enabled", "Next Run")

        rows = conn.execute(
            "SELECT name, cron_expr, enabled, next_run FROM schedules ORDER BY next_run LIMIT 5"
        ).fetchall()

        if not rows:
            table.add_row("—", "—", "—", "No schedules configured")
            return

        from ascend.scheduler import describe_cron

        for r in rows:
            desc = describe_cron(r["cron_expr"]) if r["cron_expr"] else r["cron_expr"]
            table.add_row(
                r["name"],
                desc,
                "Yes" if r["enabled"] else "No",
                r["next_run"] or "-",
            )

    def _load_meetings(self, conn) -> None:
        from datetime import datetime, timedelta

        table = self.query_one("#recent-meetings-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Date", "Member", "Summary")

        seven_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        rows = conn.execute(
            """SELECT m.date, mem.name as member_name, m.summary
               FROM meetings m
               LEFT JOIN members mem ON mem.id = m.member_id
               WHERE m.date >= ?
               ORDER BY m.date DESC LIMIT 10""",
            (seven_ago,),
        ).fetchall()

        if not rows:
            table.add_row("—", "—", "No recent meetings")
            return

        for r in rows:
            summary = (r["summary"] or "")[:60]
            table.add_row(r["date"], r["member_name"] or "—", summary)
