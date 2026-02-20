"""Coaching screen — risk dashboard with detail panel."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.widgets import DataTable, Markdown, Static


class CoachingPanel(Vertical):
    """Risk dashboard with coaching detail panel."""

    _row_member_ids: dict[str, int] = {}

    def compose(self) -> ComposeResult:
        yield Static("[b]Coaching — Risk Dashboard[/b]", classes="panel-title")
        with Horizontal(classes="coaching-layout"):
            with Vertical(classes="coaching-left"):
                yield DataTable(id="coaching-table", classes="coaching-table")
            with ScrollableContainer(classes="coaching-right"):
                yield Markdown("*Select a member to view risk details*", id="coaching-detail")

    def on_mount(self) -> None:
        table = self.query_one("#coaching-table", DataTable)
        table.cursor_type = "row"
        self.refresh_data()

    def refresh_data(self) -> None:
        from ascend.config import DB_PATH
        from ascend.db import get_connection

        if not DB_PATH.exists():
            return

        conn = get_connection(DB_PATH)
        try:
            self._load_risks(conn)
        finally:
            conn.close()

    def _load_risks(self, conn) -> None:
        from ascend.commands.coach import _compute_risks

        table = self.query_one("#coaching-table", DataTable)
        table.clear(columns=True)
        self._row_member_ids.clear()

        table.add_columns("Member", "Score", "Signals", "Status")

        members = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM members WHERE status = 'active' ORDER BY name"
            ).fetchall()
        ]

        risk_reports = []
        for m in members:
            r = _compute_risks(m, conn)
            risk_reports.append(r)

        risk_reports.sort(key=lambda x: x["risk_score"], reverse=True)

        # Store full risk data for detail view
        self._risk_data: dict[int, dict] = {}

        for r in risk_reports:
            signals_count = len(r["signals"])
            if r["risk_score"] >= 50:
                status = "High Risk"
            elif r["risk_score"] >= 25:
                status = "Medium"
            elif r["signals"]:
                status = "Low"
            else:
                status = "Clear"

            row_key = table.add_row(
                r["member"],
                str(r["risk_score"]),
                str(signals_count),
                status,
            )
            self._row_member_ids[str(row_key)] = r["member_id"]
            self._risk_data[r["member_id"]] = r

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is None:
            return
        member_id = self._row_member_ids.get(str(event.row_key))
        if member_id is not None:
            self._show_risk_detail(member_id)

    def _show_risk_detail(self, member_id: int) -> None:
        risk = self._risk_data.get(member_id)
        if not risk:
            return

        parts = [f"## {risk['member']}"]
        parts.append(f"**Risk Score:** {risk['risk_score']}/100\n")

        if risk["signals"]:
            parts.append("### Signals\n")
            for signal in risk["signals"]:
                parts.append(f"- {signal}")
        else:
            parts.append("*No risk signals detected*")

        if risk.get("details"):
            parts.append("\n### Details\n")
            for k, v in risk["details"].items():
                label = k.replace("_", " ").title()
                parts.append(f"- **{label}:** {v}")

        # Load coaching entries
        from ascend.config import DB_PATH
        from ascend.db import get_connection

        if DB_PATH.exists():
            conn = get_connection(DB_PATH)
            try:
                entries = conn.execute(
                    """SELECT kind, content, created_at FROM coaching_entries
                       WHERE member_id = ? ORDER BY created_at DESC LIMIT 5""",
                    (member_id,),
                ).fetchall()
                if entries:
                    parts.append("\n### Recent Coaching Entries\n")
                    for e in entries:
                        content = e["content"][:200]
                        parts.append(f"**{e['kind']}** ({e['created_at']})")
                        parts.append(f"> {content}\n")

                # STAR assessments
                star_entries = conn.execute(
                    """SELECT content, created_at FROM coaching_entries
                       WHERE member_id = ? AND kind = 'star_assessment'
                       ORDER BY created_at DESC LIMIT 3""",
                    (member_id,),
                ).fetchall()
                if star_entries:
                    import json

                    parts.append("\n### STAR Assessments\n")
                    for e in star_entries:
                        try:
                            star = json.loads(e["content"])
                            parts.append(f"**{e['created_at']}**")
                            parts.append(f"- **Situation:** {star.get('situation', '')}")
                            parts.append(f"- **Task:** {star.get('task', '')}")
                            parts.append(f"- **Action:** {star.get('action', '')}")
                            parts.append(f"- **Result:** {star.get('result', '')}")
                            parts.append("")
                        except (json.JSONDecodeError, TypeError):
                            pass
            finally:
                conn.close()

        md = self.query_one("#coaching-detail", Markdown)
        md.update("\n".join(parts))
