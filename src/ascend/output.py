"""Output formatting — ANSI terminal colors, JSON mode, clipboard."""

from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_RED = "\033[31m"
_CYAN = "\033[36m"


def _colorize(text: str) -> str:
    """Apply ANSI colors to markdown-formatted report text."""
    lines = []
    for line in text.split("\n"):
        if line.startswith("# ") or line.startswith("## "):
            lines.append(f"{_BOLD}{_CYAN}{line}{_RESET}")
        elif line.startswith("### "):
            lines.append(f"{_BOLD}{line}{_RESET}")
        elif "Blocked" in line:
            lines.append(f"{_RED}{line}{_RESET}")
        elif "Active" in line or "On Track" in line:
            lines.append(f"{_GREEN}{line}{_RESET}")
        elif "At Risk" in line:
            lines.append(f"{_YELLOW}{line}{_RESET}")
        elif line.startswith("Generated:") or line.startswith("---"):
            lines.append(f"{_DIM}{line}{_RESET}")
        else:
            lines.append(line)
    return "\n".join(lines)


def print_report(text: str, *, use_color: bool | None = None) -> None:
    """Print report text, with optional ANSI coloring for TTY."""
    if use_color is None:
        use_color = sys.stdout.isatty()
    output = _colorize(text) if use_color else text
    print(output)


def print_json(data: Any) -> None:
    """Print data as formatted JSON to stdout."""
    print(json.dumps(data, indent=2, default=str))


def print_status(message: str) -> None:
    """Print a status message to stderr (doesn't interfere with piped stdout)."""
    if sys.stderr.isatty():
        sys.stderr.write(f"{_DIM}{message}{_RESET}\n")
    else:
        sys.stderr.write(f"{message}\n")


def copy_to_clipboard(text: str) -> bool:
    """Copy text to clipboard via pbcopy (macOS)."""
    try:
        proc = subprocess.run(
            ["pbcopy"],
            input=text.encode("utf-8"),
            timeout=5,
        )
        return proc.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


def format_table(headers: list[str], rows: list[list[str]]) -> str:
    """Format data as a markdown table."""
    if not rows:
        return "No data."

    # Calculate column widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))

    # Build table
    lines = []
    header_line = "| " + " | ".join(h.ljust(w) for h, w in zip(headers, widths)) + " |"
    sep_line = "|-" + "-|-".join("-" * w for w in widths) + "-|"
    lines.append(header_line)
    lines.append(sep_line)
    for row in rows:
        cells = []
        for i, w in enumerate(widths):
            cell = str(row[i]) if i < len(row) else ""
            cells.append(cell.ljust(w))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def render_output(data: Any, *, json_mode: bool = False, copy: bool = False) -> None:
    """Unified output handler. JSON mode prints raw JSON; otherwise markdown."""
    if json_mode:
        text = json.dumps(data, indent=2, default=str)
        print(text)
        if copy:
            copy_to_clipboard(text)
    elif isinstance(data, str):
        print_report(data)
        if copy:
            copy_to_clipboard(data)
    else:
        text = json.dumps(data, indent=2, default=str)
        print(text)
        if copy:
            copy_to_clipboard(text)
