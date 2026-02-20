"""Schedules screen — schedule manager with enable/disable/run."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Static


class SchedulesPanel(Vertical):
    """Schedule manager with toggle actions."""

    BINDINGS = [
        Binding("e", "enable_schedule", "Enable", show=False),
        Binding("d", "disable_schedule", "Disable", show=False),
        Binding("space", "run_schedule", "Run Now", show=False),
    ]

    _row_schedule_names: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        yield Static("[b]Schedules[/b]", classes="panel-title")
        with Vertical(classes="schedules-layout"):
            yield DataTable(id="schedules-table", classes="schedules-table")
            with Horizontal(classes="schedule-actions"):
                yield Button("Enable [e]", id="btn-enable", variant="success")
                yield Button("Disable [d]", id="btn-disable", variant="warning")
                yield Button("Run Now [space]", id="btn-run", variant="primary")

    def on_mount(self) -> None:
        table = self.query_one("#schedules-table", DataTable)
        table.cursor_type = "row"
        self.refresh_data()

    def refresh_data(self) -> None:
        from ascend.config import DB_PATH
        from ascend.db import get_connection

        if not DB_PATH.exists():
            return

        conn = get_connection(DB_PATH)
        try:
            table = self.query_one("#schedules-table", DataTable)
            table.clear(columns=True)
            self._row_schedule_names.clear()

            table.add_columns("Name", "Command", "Schedule", "Enabled", "Last Run", "Next Run")

            rows = conn.execute(
                "SELECT * FROM schedules ORDER BY name"
            ).fetchall()

            if not rows:
                table.add_row("—", "No schedules configured", "—", "—", "—", "—")
                return

            from ascend.scheduler import describe_cron

            for r in rows:
                desc = describe_cron(r["cron_expr"]) if r["cron_expr"] else r["cron_expr"]
                row_key = table.add_row(
                    r["name"],
                    r["command"],
                    desc,
                    "Yes" if r["enabled"] else "No",
                    r["last_run"] or "—",
                    r["next_run"] or "—",
                )
                self._row_schedule_names[str(row_key)] = r["name"]
        finally:
            conn.close()

    def _get_selected_name(self) -> str | None:
        table = self.query_one("#schedules-table", DataTable)
        if table.cursor_row is None:
            return None
        try:
            row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
            return self._row_schedule_names.get(str(row_key))
        except Exception:
            return None

    def action_enable_schedule(self) -> None:
        name = self._get_selected_name()
        if not name or name == "—":
            return
        self._toggle_schedule(name, enable=True)

    def action_disable_schedule(self) -> None:
        name = self._get_selected_name()
        if not name or name == "—":
            return
        self._toggle_schedule(name, enable=False)

    def action_run_schedule(self) -> None:
        name = self._get_selected_name()
        if not name or name == "—":
            return
        self._run_schedule(name)

    def _toggle_schedule(self, name: str, enable: bool) -> None:
        from ascend.config import DB_PATH
        from ascend.db import get_connection

        if not DB_PATH.exists():
            return

        conn = get_connection(DB_PATH)
        try:
            if enable:
                from ascend.scheduler import compute_next_run

                row = conn.execute(
                    "SELECT cron_expr FROM schedules WHERE name = ?", (name,)
                ).fetchone()
                if row:
                    next_run = compute_next_run(row["cron_expr"])
                    conn.execute(
                        "UPDATE schedules SET enabled = 1, next_run = ? WHERE name = ?",
                        (next_run, name),
                    )
            else:
                conn.execute(
                    "UPDATE schedules SET enabled = 0, next_run = NULL WHERE name = ?",
                    (name,),
                )
            conn.commit()
        finally:
            conn.close()

        action = "enabled" if enable else "disabled"
        self.app.notify(f"Schedule '{name}' {action}")
        self.refresh_data()

    def _run_schedule(self, name: str) -> None:
        from ascend.config import DB_PATH
        from ascend.db import get_connection

        if not DB_PATH.exists():
            return

        conn = get_connection(DB_PATH)
        try:
            row = conn.execute(
                "SELECT command, cron_expr FROM schedules WHERE name = ?", (name,)
            ).fetchone()
            if not row:
                return

            import shlex
            from datetime import datetime

            from ascend.cli import main as ascend_main
            from ascend.scheduler import compute_next_run

            argv = shlex.split(row["command"])
            try:
                ascend_main(argv)
            except SystemExit:
                pass

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            next_run = compute_next_run(row["cron_expr"])
            conn.execute(
                "UPDATE schedules SET last_run = ?, next_run = ? WHERE name = ?",
                (now_str, next_run, name),
            )
            conn.commit()
        finally:
            conn.close()

        self.app.notify(f"Schedule '{name}' executed")
        self.refresh_data()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id == "btn-enable":
            self.action_enable_schedule()
        elif btn_id == "btn-disable":
            self.action_disable_schedule()
        elif btn_id == "btn-run":
            self.action_run_schedule()
