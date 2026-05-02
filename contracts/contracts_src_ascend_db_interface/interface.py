# === Ascend SQLite Database Layer (contracts_src_ascend_db_interface) v1 ===
#  Dependencies: sqlite3, pathlib
# SQLite database layer for the Ascend engineering management CLI. Provides connection management, schema initialization with versioning, and health checks for a database storing teams, members, meetings, goals, performance snapshots, coaching entries, and schedules. Implements full-text search on meeting transcripts using FTS5.

# Module invariants:
#   - SCHEMA_VERSION constant is 2
#   - _SCHEMA_SQL contains CREATE TABLE IF NOT EXISTS statements for: schema_version, teams, members, member_flags, team_members, meetings, meeting_items, goals, performance_snapshots, coaching_entries, schedules
#   - _SCHEMA_SQL creates FTS5 virtual table meetings_fts for full-text search
#   - _SCHEMA_SQL creates triggers (meetings_ai, meetings_ad, meetings_au) to sync meetings table with meetings_fts
#   - All connections use WAL journal mode
#   - All connections have foreign key constraints enabled
#   - All connections use sqlite3.Row as row_factory
#   - check_db expects tables: members, member_flags, teams, team_members, meetings, meeting_items, goals, performance_snapshots, coaching_entries, schedules

Path = primitive  # pathlib.Path - filesystem path object

Connection = primitive  # sqlite3.Connection - database connection object

Row = primitive  # sqlite3.Row - row factory for dict-like access to query results

class HealthCheckResult:
    """Dictionary returned by check_db with health status"""
    ok: bool                                 # required, True if database is healthy, False otherwise
    error: str = None                        # optional, Error message if ok is False
    version: int = None                      # optional, Schema version number if ok is True
    tables: dict = None                      # optional, Dictionary mapping table names to row counts if ok is True

def get_connection(
    db_path: Path,
) -> Connection:
    """
    Opens a SQLite connection with Write-Ahead Logging (WAL) mode enabled and foreign key constraints enforced. Sets row_factory to sqlite3.Row for dict-like access to query results.

    Preconditions:
      - db_path is a valid Path object

    Postconditions:
      - Returns an open sqlite3.Connection
      - Connection has WAL journal mode enabled
      - Connection has foreign key enforcement enabled
      - Connection row_factory is set to sqlite3.Row

    Errors:
      - file_access_error (sqlite3.OperationalError): db_path directory doesn't exist or insufficient permissions
      - invalid_path (TypeError): db_path cannot be converted to string

    Side effects: Opens file connection to db_path, Creates database file if it doesn't exist, Executes PRAGMA journal_mode=WAL on connection, Executes PRAGMA foreign_keys=ON on connection
    Idempotent: yes
    """
    ...

def init_db(
    db_path: Path,
) -> Connection:
    """
    Creates the database file (if needed), applies the schema if not present or outdated, and returns an open connection. Checks current schema version and only applies schema updates if current version is less than SCHEMA_VERSION (2). Creates parent directories if they don't exist.

    Preconditions:
      - db_path is a valid Path object

    Postconditions:
      - Database file exists at db_path
      - All parent directories of db_path exist
      - Schema is at SCHEMA_VERSION (2)
      - schema_version table has entry for SCHEMA_VERSION
      - All tables, triggers, and FTS5 virtual tables are created
      - Returns open connection with WAL mode and foreign keys enabled

    Errors:
      - permission_error (PermissionError): Insufficient permissions to create directories or database file
      - sql_error (sqlite3.Error): Invalid SQL in _SCHEMA_SQL or execution failure
      - operational_error (sqlite3.OperationalError): Database is locked or corrupted during schema application

    Side effects: Creates parent directories if missing, Creates database file if it doesn't exist, Executes schema SQL script if version is outdated, Inserts schema version record, Commits transaction if schema is applied
    Idempotent: yes
    """
    ...

def check_db(
    db_path: Path,
) -> HealthCheckResult:
    """
    Performs health check on the database by verifying existence, schema initialization, and returning table row counts. Returns a dictionary with ok status, version, and table counts. If database doesn't exist or schema is uninitialized, returns error state.

    Preconditions:
      - db_path is a valid Path object

    Postconditions:
      - Returns dict with 'ok' key (bool)
      - If ok=False, includes 'error' key with description
      - If ok=True, includes 'version' (int) and 'tables' (dict) keys
      - Connection is closed before returning

    Errors:
      - database_not_found (return value): db_path.exists() returns False
          ok: False
          error: Database not found
      - schema_not_initialized (return value): schema_version table doesn't exist (sqlite3.OperationalError)
          ok: False
          error: Schema not initialized
      - sql_error (sqlite3.Error): Query execution fails on table count (table doesn't exist)

    Side effects: Opens and closes database connection, Executes SELECT queries on schema_version and all tables
    Idempotent: yes
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['HealthCheckResult', 'get_connection', 'init_db', 'check_db', 'return value']
