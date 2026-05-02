# === Audit Log Interface (contracts_src_ascend_audit_interface) v1 ===
#  Dependencies: json, datetime, pathlib, typing, ascend.config
# Append-only JSONL audit log for recording and reading operation history. Provides functions to log commands with arguments, results, and errors, and to retrieve recent audit entries.

# Module invariants:
#   - Audit log is append-only (never modified or deleted by this module)
#   - Each audit entry is a single JSON line (JSONL format)
#   - All timestamps are in UTC and ISO8601 format
#   - Audit file path is always HISTORY_DIR/audit.jsonl

class AuditEntry:
    """Structure of an audit log entry (not explicitly defined but implied by usage)"""
    timestamp: str                           # required, ISO8601 UTC timestamp
    command: str                             # required, Command that was executed
    args: Optional[dict] = None              # optional, Command arguments
    result: Optional[str] = None             # optional, Result of the command
    error: Optional[str] = None              # optional, Error message if command failed

def _audit_path() -> Path:
    """
    Returns the Path object for the audit log file (audit.jsonl in HISTORY_DIR).

    Preconditions:
      - HISTORY_DIR must be defined in ascend.config

    Postconditions:
      - Returns Path object pointing to HISTORY_DIR/audit.jsonl

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
    Append an operation to the audit log. Creates parent directories if they don't exist. Writes a JSON line with timestamp, command, and optional args, result, and error fields.

    Preconditions:
      - command must be a valid string

    Postconditions:
      - Parent directory of audit log exists
      - A new JSON line is appended to the audit log file
      - Entry contains ISO8601 UTC timestamp and command
      - Entry contains args, result, error only if provided and truthy

    Errors:
      - file_write_error (OSError): Unable to write to audit file due to permissions or disk space
      - json_serialization_error (TypeError): Arguments contain non-serializable objects (mitigated by default=str)

    Side effects: Creates directories (parents=True, exist_ok=True), Appends to audit.jsonl file
    Idempotent: no
    """
    ...

def read_audit(
    last_n: int = 50,
) -> list[dict[str, Any]]:
    """
    Read recent audit entries from the audit log. Returns the last N entries (default 50). Returns empty list if audit file does not exist.

    Postconditions:
      - Returns empty list if audit file doesn't exist
      - Returns at most last_n entries
      - Entries are returned in chronological order (oldest to newest of the last_n)
      - Empty lines in the file are skipped

    Errors:
      - file_read_error (OSError): Unable to read audit file due to permissions
      - json_decode_error (json.JSONDecodeError): Malformed JSON line in audit file

    Side effects: none
    Idempotent: yes
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['AuditEntry', '_audit_path', 'log_operation', 'read_audit']
