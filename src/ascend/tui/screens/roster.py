"""Roster screen — member list with detail sidebar."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Input, Static

from ascend.tui.widgets.member_card import MemberCard


class RosterPanel(Vertical):
    """Member roster with filterable table and detail sidebar."""

    BINDINGS = [
        Binding("slash", "focus_filter", "Filter", show=False),
        Binding("f", "flag_member", "Flag", show=False),
    ]

    # Map row keys to member IDs
    _row_member_ids: dict[str, int] = {}

    def compose(self) -> ComposeResult:
        yield Static("[b]Roster[/b]", classes="panel-title")
        with Horizontal(classes="roster-layout"):
            with Vertical(classes="roster-left"):
                yield Input(placeholder="Filter members...", id="roster-filter", classes="filter-input")
                yield DataTable(id="roster-table", classes="roster-table")
            with Vertical(classes="roster-right"):
                yield MemberCard()

    def on_mount(self) -> None:
        table = self.query_one("#roster-table", DataTable)
        table.cursor_type = "row"
        self.refresh_data()

    def refresh_data(self, filter_text: str = "") -> None:
        from ascend.config import DB_PATH
        from ascend.db import get_connection

        if not DB_PATH.exists():
            return

        conn = get_connection(DB_PATH)
        try:
            table = self.query_one("#roster-table", DataTable)
            table.clear(columns=True)
            self._row_member_ids.clear()

            table.add_columns("Name", "Team", "Title", "Status", "Flags")

            query = """
                SELECT m.*, t.name as team_name
                FROM members m
                LEFT JOIN teams t ON t.id = m.team_id
                WHERE m.status != 'inactive'
            """
            params: list = []

            if filter_text:
                query += """ AND (
                    m.name LIKE ? OR m.github LIKE ? OR m.title LIKE ?
                    OR m.email LIKE ? OR t.name LIKE ?
                    OR m.id IN (SELECT member_id FROM member_flags WHERE flag LIKE ?)
                )"""
                like = f"%{filter_text}%"
                params.extend([like] * 6)

            query += " ORDER BY m.name"
            rows = conn.execute(query, params).fetchall()

            for r in rows:
                m = dict(r)
                flags = [
                    f["flag"]
                    for f in conn.execute(
                        "SELECT flag FROM member_flags WHERE member_id = ?",
                        (m["id"],),
                    ).fetchall()
                ]
                row_key = table.add_row(
                    m["name"],
                    m.get("team_name") or "",
                    m.get("title") or "",
                    m["status"],
                    ", ".join(flags),
                )
                self._row_member_ids[str(row_key)] = m["id"]
        finally:
            conn.close()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "roster-filter":
            self.refresh_data(filter_text=event.value)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.row_key is not None:
            member_id = self._row_member_ids.get(str(event.row_key))
            if member_id is not None:
                card = self.query_one(MemberCard)
                card.show_member(member_id)

    def select_member(self, member_id: int) -> None:
        """Select a member by ID (from command palette)."""
        for row_key_str, mid in self._row_member_ids.items():
            if mid == member_id:
                table = self.query_one("#roster-table", DataTable)
                # Find the RowKey object
                for rk in table.rows:
                    if str(rk) == row_key_str:
                        table.move_cursor(row=table.get_row_index(rk))
                        break
                card = self.query_one(MemberCard)
                card.show_member(member_id)
                break

    def action_focus_filter(self) -> None:
        self.query_one("#roster-filter", Input).focus()

    def action_flag_member(self) -> None:
        table = self.query_one("#roster-table", DataTable)
        if table.cursor_row is not None:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            member_id = self._row_member_ids.get(str(row_key))
            if member_id:
                self.app.notify(f"Use CLI: ascend roster flag {member_id} <flag>")
