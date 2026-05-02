# === Output Formatter (contracts_src_ascend_output_interface) v1 ===
#  Dependencies: json, subprocess, sys, typing
# Output formatting utilities for terminal output with ANSI colors, JSON serialization, clipboard integration, and markdown table formatting. Provides functions for colorizing markdown-formatted reports, printing to stdout/stderr, copying to clipboard via pbcopy, and unified output rendering.

# Module invariants:
#   - ANSI color codes are constant: RESET='\033[0m', BOLD='\033[1m', DIM='\033[2m', GREEN='\033[32m', YELLOW='\033[33m', RED='\033[31m', CYAN='\033[36m'
#   - JSON serialization always uses indent=2 and default=str
#   - Clipboard operations use pbcopy command with 5-second timeout
#   - Status messages always go to stderr, reports to stdout
#   - Color auto-detection uses sys.stdout.isatty() for print_report and sys.stderr.isatty() for print_status

def _colorize(
    text: str,
) -> str:
    """
    Apply ANSI color codes to markdown-formatted report text based on line patterns. Colors headers (#, ##, ###), status indicators (Blocked, Active, On Track, At Risk), and metadata lines (Generated:, ---).

    Postconditions:
      - Returns string with ANSI escape codes inserted
      - Output string contains original text content with added color codes
      - Lines starting with '# ' or '## ' are bold cyan
      - Lines starting with '### ' are bold
      - Lines containing 'Blocked' are red
      - Lines containing 'Active' or 'On Track' are green
      - Lines containing 'At Risk' are yellow
      - Lines starting with 'Generated:' or '---' are dimmed

    Side effects: none
    Idempotent: yes
    """
    ...

def print_report(
    text: str,
    use_color: bool | None = None,
) -> None:
    """
    Print report text to stdout with optional ANSI coloring. If use_color is None, auto-detects TTY and enables colors for interactive terminals.

    Postconditions:
      - Text is printed to stdout
      - If use_color is True or (None and stdout is a TTY), text is colorized
      - If use_color is False or (None and stdout is not a TTY), text is printed as-is

    Side effects: Writes to stdout
    Idempotent: no
    """
    ...

def print_json(
    data: Any,
) -> None:
    """
    Print data as formatted JSON to stdout with 2-space indentation. Uses str as default serializer for non-JSON-serializable types.

    Postconditions:
      - Data is serialized to JSON with indent=2
      - JSON output is printed to stdout
      - Non-serializable objects are converted to strings

    Side effects: Writes to stdout
    Idempotent: no
    """
    ...

def print_status(
    message: str,
) -> None:
    """
    Print a status message to stderr without interfering with piped stdout. Dims the message if stderr is a TTY.

    Postconditions:
      - Message is written to stderr with newline
      - If stderr is a TTY, message is dimmed with ANSI codes
      - If stderr is not a TTY, message is written as-is

    Side effects: Writes to stderr
    Idempotent: no
    """
    ...

def copy_to_clipboard(
    text: str,
) -> bool:
    """
    Copy text to system clipboard via pbcopy command (macOS only). Returns True on success, False on failure. Has 5-second timeout.

    Postconditions:
      - Returns True if pbcopy command succeeds (returncode == 0)
      - Returns False if pbcopy times out, is not found, or OS error occurs
      - On success, text is in system clipboard

    Errors:
      - timeout (subprocess.TimeoutExpired): pbcopy subprocess exceeds 5-second timeout
          handling: Caught and returns False
      - pbcopy_not_found (FileNotFoundError): pbcopy command not found on system
          handling: Caught and returns False
      - os_error (OSError): OS-level error executing subprocess
          handling: Caught and returns False

    Side effects: Executes pbcopy subprocess, Modifies system clipboard
    Idempotent: no
    """
    ...

def format_table(
    headers: list[str],
    rows: list[list[str]],
) -> str:
    """
    Format data as a markdown table with aligned columns. Returns 'No data.' if rows list is empty. Calculates column widths based on headers and row content.

    Postconditions:
      - Returns 'No data.' if rows list is empty
      - Returns markdown-formatted table string if rows exist
      - Table has header row, separator row, and data rows
      - Columns are left-justified and padded to consistent widths
      - Cells are converted to strings
      - Missing cells (row shorter than headers) are rendered as empty strings

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
    Unified output handler that prints data as JSON or markdown and optionally copies to clipboard. In json_mode, serializes any data to JSON. Otherwise, prints strings as reports or serializes non-strings to JSON.

    Postconditions:
      - If json_mode is True: data is serialized to JSON and printed to stdout
      - If json_mode is False and data is str: data is printed as colored report
      - If json_mode is False and data is not str: data is serialized to JSON and printed
      - If copy is True: output text is copied to clipboard via copy_to_clipboard

    Side effects: Prints to stdout, May copy to clipboard
    Idempotent: no
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['_colorize', 'print_report', 'print_json', 'print_status', 'copy_to_clipboard', 'format_table', 'render_output']
