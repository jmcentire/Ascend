"""MemberCard widget — member detail panel for sidebar."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import ScrollableContainer
from textual.widget import Widget
from textual.widgets import Static

from ascend.tui.widgets.metric_bar import MetricBar


class MemberCard(Widget):
    """Right sidebar showing selected member details."""

    def compose(self) -> ComposeResult:
        with ScrollableContainer(classes="member-card-content"):
            yield Static("[dim]Select a member to view details[/]", id="card-placeholder", classes="card-empty")
            yield Static("", id="card-name")
            yield Static("", id="card-title")
            yield Static("", id="card-email")
            yield Static("", id="card-github")
            yield Static("", id="card-slack")
            yield Static("", id="card-status")
            yield Static("", id="card-flags")
            yield Static("", id="card-team")
            yield MetricBar(label="Score", id="card-score-bar")
            yield Static("", id="card-meetings")
            yield Static("", id="card-items")

    def on_mount(self) -> None:
        self._hide_fields()

    def _hide_fields(self) -> None:
        for widget in self.query("Static, MetricBar"):
            if widget.id and widget.id != "card-placeholder":
                widget.display = False
        try:
            self.query_one("#card-placeholder").display = True
        except Exception:
            pass

    def _show_fields(self) -> None:
        try:
            self.query_one("#card-placeholder").display = False
        except Exception:
            pass
        for widget in self.query("Static, MetricBar"):
            if widget.id and widget.id != "card-placeholder":
                widget.display = True

    def show_member(self, member_id: int) -> None:
        """Load and display member details from DB."""
        from ascend.config import DB_PATH
        from ascend.db import get_connection

        if not DB_PATH.exists():
            return

        conn = get_connection(DB_PATH)
        try:
            row = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
            if not row:
                return
            m = dict(row)

            flags = [r["flag"] for r in conn.execute(
                "SELECT flag FROM member_flags WHERE member_id = ?", (member_id,)
            ).fetchall()]

            team_name = None
            if m.get("team_id"):
                team_row = conn.execute("SELECT name FROM teams WHERE id = ?", (m["team_id"],)).fetchone()
                if team_row:
                    team_name = team_row["name"]

            meeting_count = conn.execute(
                "SELECT COUNT(*) FROM meetings WHERE member_id = ?", (member_id,)
            ).fetchone()[0]

            last_meeting = conn.execute(
                "SELECT date FROM meetings WHERE member_id = ? ORDER BY date DESC LIMIT 1",
                (member_id,),
            ).fetchone()

            open_items = conn.execute(
                """SELECT COUNT(*) FROM meeting_items mi
                   JOIN meetings mt ON mt.id = mi.meeting_id
                   WHERE mt.member_id = ? AND mi.status = 'open'""",
                (member_id,),
            ).fetchone()[0]

            # Get avg score from last 30 days
            from datetime import datetime, timedelta
            thirty_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            snapshots = conn.execute(
                "SELECT score FROM performance_snapshots WHERE member_id = ? AND date >= ?",
                (member_id, thirty_ago),
            ).fetchall()
            avg_score = 0.0
            if snapshots:
                scores = [s["score"] or 0 for s in snapshots]
                avg_score = sum(scores) / len(scores)

        finally:
            conn.close()

        self._show_fields()

        self.query_one("#card-name", Static).update(f"[b]{m['name']}[/b]")
        self.query_one("#card-title", Static).update(f"[b]Title:[/] {m.get('title') or '-'}")
        self.query_one("#card-email", Static).update(f"[b]Email:[/] {m.get('email') or '-'}")
        self.query_one("#card-github", Static).update(f"[b]GitHub:[/] @{m.get('github') or '-'}")
        self.query_one("#card-slack", Static).update(f"[b]Slack:[/] {m.get('slack') or '-'}")
        self.query_one("#card-status", Static).update(f"[b]Status:[/] {m.get('status', 'active')}")
        self.query_one("#card-flags", Static).update(
            f"[b]Flags:[/] {', '.join(flags)}" if flags else "[b]Flags:[/] none"
        )
        self.query_one("#card-team", Static).update(f"[b]Team:[/] {team_name or '-'}")

        bar = self.query_one("#card-score-bar", MetricBar)
        bar.value = avg_score
        bar.max_value = 50.0

        last_date = last_meeting["date"] if last_meeting else "never"
        self.query_one("#card-meetings", Static).update(
            f"[b]Meetings:[/] {meeting_count} (last: {last_date})"
        )
        self.query_one("#card-items", Static).update(f"[b]Open items:[/] {open_items}")

    def clear_card(self) -> None:
        self._hide_fields()
