# === Ascend Audit Interface (contracts_contracts_src_ascend_audit_interface_interface) v1 ===
#  Dependencies: json, datetime, pathlib, typing, ascend.config
# Append-only JSONL audit log for recording and reading operation history. Provides functions to log operations (commands, arguments, results, errors) with timestamps and retrieve recent audit entries.

# Module invariants:
#   - Audit log is append-only (no modification or deletion of existing entries)
#   - Each entry is a single line of JSON followed by newline
#   - All timestamps are in UTC ISO format
#   - File path is always HISTORY_DIR/audit.jsonl
#   - Entries maintain chronological order (newest at end)

class AuditEntry:
    """Structure of an audit log entry (not explicitly defined as a class, but implicitly used as a dict)"""
    timestamp: str                           # required, ISO format UTC timestamp
    command: str                             # required, Command or operation name
    args: dict = None                        # optional, Optional arguments dictionary
    result: str = None                       # optional, Optional result string
    error: str = None                        # optional, Optional error string

def _audit_path() -> Path:
    """
    Returns the Path object for the audit log file (HISTORY_DIR/audit.jsonl). Internal helper function.

    Preconditions:
      - HISTORY_DIR constant must be defined in ascend.config

    Postconditions:
      - Returns a Path object pointing to audit.jsonl within HISTORY_DIR

    Side effects: none
    Idempotent: yes
    """
    ...

def log_operation(
    command: str,
    args: Optional[dict] = None,
    result: Optional[str] = None,
    error: Optional[str] = None,
) -> None:
    """
    Appends an operation entry to the audit log as a JSONL record. Creates parent directories if they don't exist. Records timestamp, command, and optional args/result/error fields.

    Preconditions:
      - command must be a non-empty string

    Postconditions:
      - A new line is appended to audit.jsonl
      - Entry contains UTC timestamp, command, and any provided optional fields
      - Parent directory of audit.jsonl exists
      - File handle is closed after write

    Errors:
      - file_write_error (IOError): When file cannot be opened for writing
      - directory_creation_error (OSError): When parent directory creation fails due to permissions or other OS errors
      - serialization_error (TypeError): When json.dumps fails to serialize entry fields (though default=str fallback mitigates this)

    Side effects: Creates HISTORY_DIR and parent directories if they don't exist, Appends a JSONL entry to audit.jsonl file
    Idempotent: no
    """
    ...

def read_audit(
    last_n: int = 50,
) -> list[dict[str, Any]]:
    """
    Reads and returns the last N entries from the audit log. Returns empty list if audit file doesn't exist. Skips blank lines.

    Postconditions:
      - Returns a list of at most last_n audit entry dictionaries
      - Returns empty list if audit file does not exist
      - Entries are in chronological order (oldest to newest of the returned slice)
      - Blank lines in the file are skipped

    Errors:
      - file_read_error (IOError): When file exists but cannot be read due to permissions
      - json_parse_error (json.JSONDecodeError): When a non-blank line contains invalid JSON

    Side effects: none
    Idempotent: yes
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['AuditEntry', '_audit_path', 'log_operation', 'read_audit']
