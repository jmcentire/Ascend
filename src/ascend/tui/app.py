"""AscendApp — main TUI application."""

from __future__ import annotations

from functools import partial

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.command import Hit, Hits, Provider
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    ContentSwitcher,
    Footer,
    Header,
    Markdown,
    Static,
)

NAV_ITEMS = [
    ("dashboard", "Dashboard", "1"),
    ("roster", "Roster", "2"),
    ("meetings", "Meetings", "3"),
    ("reports", "Reports", "4"),
    ("coaching", "Coaching", "5"),
    ("schedules", "Schedules", "6"),
]

HELP_TEXT = """\
# Keyboard Shortcuts

| Key | Action |
|-----|--------|
| **1**–**6** | Switch screens |
| **Ctrl+P** | Command palette |
| **r** | Refresh current view |
| **q** | Quit |
| **?** | This help |
| **Escape** | Close overlay / go back |
| **Enter** | Select / drill into detail |
| **/** | Focus search / filter |
| **j** / **k** | Navigate rows |

## Screens

1. **Dashboard** — Org overview, risk alerts, schedules
2. **Roster** — Member list with detail sidebar
3. **Meetings** — Meeting list with transcript viewer
4. **Reports** — Performance, team, git, progress reports
5. **Coaching** — Risk dashboard, STAR assessments
6. **Schedules** — Schedule manager
"""


class AscendCommands(Provider):
    """Command palette provider."""

    async def search(self, query: str) -> Hits:
        matcher = self.matcher(query)
        for panel_id, label, key in NAV_ITEMS:
            score = matcher.match(label)
            if score > 0:
                yield Hit(
                    score,
                    matcher.highlight(label),
                    partial(self.app.action_switch_panel, panel_id),
                    help=f"Switch to {label} [{key}]",
                )
        from ascend.config import DB_PATH
        from ascend.db import get_connection

        if DB_PATH.exists():
            conn = get_connection(DB_PATH)
            try:
                rows = conn.execute(
                    "SELECT id, name FROM members WHERE status = 'active' ORDER BY name"
                ).fetchall()
                for row in rows:
                    score = matcher.match(row["name"])
                    if score > 0:
                        yield Hit(
                            score,
                            matcher.highlight(row["name"]),
                            partial(self.app.action_show_member, row["id"]),
                            help="View member",
                        )
            finally:
                conn.close()


class HelpScreen(ModalScreen):
    """Help overlay showing keyboard shortcuts."""

    BINDINGS = [Binding("escape", "dismiss", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-dialog"):
            yield Markdown(HELP_TEXT)
            yield Static("[dim]Press Escape to close[/]", classes="help-footer")


class Sidebar(Vertical):
    """Navigation sidebar."""

    def compose(self) -> ComposeResult:
        yield Static("[b]ASCEND[/b]", classes="sidebar-title")
        for panel_id, label, key in NAV_ITEMS:
            yield Button(f" {key}  {label}", id=f"nav-{panel_id}", classes="nav-btn")


class AscendApp(App):
    """Ascend — interactive engineering management TUI."""

    TITLE = "Ascend"
    CSS_PATH = "styles/app.tcss"
    COMMANDS = {AscendCommands}

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("1", "switch_panel('dashboard')", "Dashboard", show=False),
        Binding("2", "switch_panel('roster')", "Roster", show=False),
        Binding("3", "switch_panel('meetings')", "Meetings", show=False),
        Binding("4", "switch_panel('reports')", "Reports", show=False),
        Binding("5", "switch_panel('coaching')", "Coaching", show=False),
        Binding("6", "switch_panel('schedules')", "Schedules", show=False),
        Binding("r", "refresh", "Refresh"),
        Binding("question_mark", "help_overlay", "Help", show=False),
    ]

    _active_panel: str = "dashboard"

    def compose(self) -> ComposeResult:
        from ascend.tui.screens.coaching import CoachingPanel
        from ascend.tui.screens.dashboard import DashboardPanel
        from ascend.tui.screens.meetings import MeetingsPanel
        from ascend.tui.screens.reports import ReportsPanel
        from ascend.tui.screens.roster import RosterPanel
        from ascend.tui.screens.schedules import SchedulesPanel

        yield Header()
        with Horizontal(id="main-layout"):
            yield Sidebar()
            with ContentSwitcher(initial="dashboard", id="content"):
                yield DashboardPanel(id="dashboard")
                yield RosterPanel(id="roster")
                yield MeetingsPanel(id="meetings")
                yield ReportsPanel(id="reports")
                yield CoachingPanel(id="coaching")
                yield SchedulesPanel(id="schedules")
        yield Footer()

    def on_mount(self) -> None:
        self._highlight_nav("dashboard")

    def _highlight_nav(self, panel_id: str) -> None:
        for btn in self.query(".nav-btn"):
            btn.remove_class("-active")
        try:
            self.query_one(f"#nav-{panel_id}", Button).add_class("-active")
        except Exception:
            pass

    def action_switch_panel(self, panel_id: str) -> None:
        switcher = self.query_one("#content", ContentSwitcher)
        switcher.current = panel_id
        self._active_panel = panel_id
        self._highlight_nav(panel_id)

    def action_refresh(self) -> None:
        panel = self.query_one(f"#{self._active_panel}")
        if hasattr(panel, "refresh_data"):
            panel.refresh_data()

    def action_show_member(self, member_id: int) -> None:
        self.action_switch_panel("roster")
        roster = self.query_one("#roster")
        if hasattr(roster, "select_member"):
            roster.select_member(member_id)

    def action_help_overlay(self) -> None:
        self.push_screen(HelpScreen())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        if btn_id.startswith("nav-"):
            panel_id = btn_id[4:]
            self.action_switch_panel(panel_id)
