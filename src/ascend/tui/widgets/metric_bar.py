"""MetricBar widget — visual score bar."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static


class MetricBar(Widget):
    """Horizontal bar showing a value as a filled proportion."""

    value: reactive[float] = reactive(0.0)
    max_value: reactive[float] = reactive(100.0)
    label: reactive[str] = reactive("")

    def __init__(
        self,
        label: str = "",
        value: float = 0.0,
        max_value: float = 100.0,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self.label = label
        self.value = value
        self.max_value = max_value

    def render(self) -> str:
        width = max(self.size.width - len(self.label) - 8, 5)
        pct = min(self.value / self.max_value, 1.0) if self.max_value > 0 else 0
        filled = int(width * pct)
        empty = width - filled
        bar = "█" * filled + "░" * empty
        pct_str = f"{pct * 100:.0f}%"
        if self.label:
            return f"{self.label} {bar} {pct_str}"
        return f"{bar} {pct_str}"

    def watch_value(self) -> None:
        self.refresh()

    def watch_max_value(self) -> None:
        self.refresh()
