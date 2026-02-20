"""Meetings screen — meeting list with transcript viewer."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Input, Markdown, Static


class MeetingsPanel(Vertical):
    """Meeting list with transcript/summary viewer."""

    BINDINGS = [
        Binding("slash", "focus_search", "Search", show=False),
    ]

    _row_meeting_ids: dict[str, int] = {}

    def compose(self) -> ComposeResult:
        yield Static("[b]Meetings[/b]", classes="panel-title")
        with Vertical(classes="meetings-layout"):
            with Vertical(classes="meetings-top"):
                yield Input(
                    placeholder="Search meetings (FTS)...",
                    id="meetings-search",
                    classes="filter-input",
                )
                yield DataTable(id="meetings-table", classes="meetings-table")
            with Vertical(classes="meetings-bottom"):
                yield Markdown("*Select a meeting to view details*", id="meeting-detail")

    def on_mount(self) -> None:
        table = self.query_one("#meetings-table", DataTable)
        table.cursor_type = "row"
        self.refresh_data()

    def refresh_data(self, search_query: str = "") -> None:
        from ascend.config import DB_PATH
        from ascend.db import get_connection

        if not DB_PATH.exists():
            return

        conn = get_connection(DB_PATH)
        try:
            table = self.query_one("#meetings-table", DataTable)
            table.clear(columns=True)
            self._row_meeting_ids.clear()

            table.add_columns("Date", "Member", "Source", "Summary")

            if search_query:
                rows = conn.execute(
                    """SELECT m.id, m.date, mem.name as member_name,
                              m.source_file, m.summary,
                              snippet(meetings_fts, 0, '>>>', '<<<', '...', 40) as snippet
                       FROM meetings_fts
                       JOIN meetings m ON m.id = meetings_fts.rowid
                       LEFT JOIN members mem ON mem.id = m.member_id
                       WHERE meetings_fts MATCH ?
                       ORDER BY rank
                       LIMIT 50""",
                    (search_query,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT m.id, m.date, mem.name as member_name,
                              m.source_file, m.summary
                       FROM meetings m
                       LEFT JOIN members mem ON mem.id = m.member_id
                       ORDER BY m.date DESC
                       LIMIT 100"""
                ).fetchall()

            for r in rows:
                summary = (r["summary"] or "")[:80]
                row_key = table.add_row(
                    r["date"],
                    r["member_name"] or "—",
                    r["source_file"] or "—",
                    summary,
                )
                self._row_meeting_ids[str(row_key)] = r["id"]

            if not rows:
                md = self.query_one("#meeting-detail", Markdown)
                md.update("*No meetings found*")
        finally:
            conn.close()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "meetings-search":
            query = event.value.strip()
            if len(query) >= 2:
                try:
                    self.refresh_data(search_query=query)
                except Exception:
                    pass
            elif not query:
                self.refresh_data()

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is None:
            return
        meeting_id = self._row_meeting_ids.get(str(event.row_key))
        if meeting_id is not None:
            self._show_meeting_detail(meeting_id)

    def _show_meeting_detail(self, meeting_id: int) -> None:
        from ascend.config import DB_PATH
        from ascend.db import get_connection

        if not DB_PATH.exists():
            return

        conn = get_connection(DB_PATH)
        try:
            row = conn.execute(
                """SELECT m.*, mem.name as member_name FROM meetings m
                   LEFT JOIN members mem ON mem.id = m.member_id
                   WHERE m.id = ?""",
                (meeting_id,),
            ).fetchone()
            if not row:
                return

            items = conn.execute(
                "SELECT kind, content, status FROM meeting_items WHERE meeting_id = ? ORDER BY kind, id",
                (meeting_id,),
            ).fetchall()
        finally:
            conn.close()

        parts = [f"## Meeting {row['id']} — {row['date']}"]
        if row["member_name"]:
            parts.append(f"**Member:** {row['member_name']}")
        if row["sentiment_score"] is not None:
            parts.append(f"**Sentiment:** {row['sentiment_score']:.2f}")
        if row["summary"]:
            parts.append(f"\n### Summary\n\n{row['summary']}")
        if items:
            parts.append("\n### Items\n")
            for item in items:
                status = "x" if item["status"] == "closed" else " "
                parts.append(f"- [{status}] **{item['kind']}**: {item['content']}")
        if row["raw_text"]:
            text = row["raw_text"][:3000]
            parts.append(f"\n### Transcript\n\n{text}")
            if len(row["raw_text"]) > 3000:
                parts.append(f"\n*... ({len(row['raw_text'])} chars total)*")

        md = self.query_one("#meeting-detail", Markdown)
        md.update("\n".join(parts))

    def action_focus_search(self) -> None:
        self.query_one("#meetings-search", Input).focus()
