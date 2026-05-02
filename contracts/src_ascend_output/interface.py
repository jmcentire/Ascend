# === Output Formatting (src_ascend_output) v1 ===
#  Dependencies: json, subprocess, sys, typing
# Output formatting module providing ANSI terminal colors, JSON serialization, clipboard integration, and markdown table rendering for the Ascend CLI tool

# Module invariants:
#   - ANSI color codes are constants: _RESET, _BOLD, _DIM, _GREEN, _YELLOW, _RED, _CYAN
#   - pbcopy timeout is fixed at 5 seconds
#   - JSON output always uses 2-space indentation and default=str for serialization

Any = primitive  # Python typing.Any for arbitrary data types

def _colorize(
    text: str,
) -> str:
    """
    Apply ANSI color codes to markdown-formatted report text based on line patterns (headers, status keywords)

    Postconditions:
      - Returns text with ANSI color codes applied
      - Headers (# and ##) are bold cyan
      - Subheaders (###) are bold
      - Lines containing 'Blocked' are red
      - Lines containing 'Active' or 'On Track' are green
      - Lines containing 'At Risk' are yellow
      - Lines starting with 'Generated:' or '---' are dim
      - Other lines remain unchanged

    Side effects: none
    Idempotent: yes
    """
    ...

def print_report(
    text: str,
    use_color: bool | None = None,
) -> None:
    """
    Print report text to stdout with optional ANSI coloring, auto-detecting TTY if use_color is not specified

    Postconditions:
      - Text is printed to stdout
      - If use_color is None, colors are applied only if stdout is a TTY
      - If use_color is True, colors are always applied
      - If use_color is False, no colors are applied

    Side effects: Prints to stdout
    Idempotent: no
    """
    ...

def print_json(
    data: Any,
) -> None:
    """
    Print data as indented JSON to stdout using default=str for non-serializable objects

    Postconditions:
      - Data is serialized to JSON with 2-space indentation
      - Non-serializable objects are converted to strings
      - JSON is printed to stdout

    Side effects: Prints to stdout
    Idempotent: no
    """
    ...

def print_status(
    message: str,
) -> None:
    """
    Print a status message to stderr with dim styling if stderr is a TTY, plain text otherwise

    Postconditions:
      - Message is printed to stderr
      - If stderr is a TTY, message is dimmed with ANSI codes
      - If stderr is not a TTY, message is printed plain

    Side effects: Writes to stderr
    Idempotent: no
    """
    ...

def copy_to_clipboard(
    text: str,
) -> bool:
    """
    Copy text to clipboard via pbcopy command (macOS-specific), with 5-second timeout

    Postconditions:
      - Returns True if pbcopy command succeeds (returncode == 0)
      - Returns False if pbcopy times out, is not found, or raises OSError

    Errors:
      - timeout (subprocess.TimeoutExpired): pbcopy does not complete within 5 seconds
          handling: Caught and returns False
      - command_not_found (FileNotFoundError): pbcopy command does not exist
          handling: Caught and returns False
      - os_error (OSError): OS-level error executing pbcopy
          handling: Caught and returns False

    Side effects: Invokes pbcopy subprocess, Modifies system clipboard on success
    Idempotent: no
    """
    ...

def format_table(
    headers: list[str],
    rows: list[list[str]],
) -> str:
    """
    Format headers and rows as a markdown table with auto-calculated column widths

    Postconditions:
      - Returns 'No data.' if rows is empty
      - Returns markdown table string if rows is non-empty
      - Column widths are calculated to fit headers and all cells
      - Table uses markdown pipe syntax with separators
      - Cells are left-justified and padded to column width
      - Missing cells in short rows are rendered as empty strings

    Side effects: none
    Idempotent: yes
    """
    ...

def render_output(
    data: Any,
    json_mode: bool = False,
    copy: bool = False,
) -> None:
    """
    Unified output handler that prints data as JSON or markdown, optionally copying to clipboard

    Postconditions:
      - If json_mode is True, data is printed as JSON to stdout
      - If json_mode is False and data is str, prints as colored report
      - If json_mode is False and data is not str, prints as JSON to stdout
      - If copy is True, attempts to copy output to clipboard via copy_to_clipboard

    Side effects: Prints to stdout, May copy to clipboard if copy=True
    Idempotent: no
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['_colorize', 'print_report', 'print_json', 'print_status', 'copy_to_clipboard', 'format_table', 'render_output']
