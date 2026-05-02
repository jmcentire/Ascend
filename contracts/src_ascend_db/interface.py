# === Ascend SQLite Database Layer (src_ascend_db) v1 ===
#  Dependencies: sqlite3, pathlib
# SQLite database layer for Ascend engineering management CLI. Provides connection management, schema initialization with versioning, and health check capabilities. Manages tables for teams, members, meetings, goals, performance snapshots, coaching entries, and schedules with full-text search support.

# Module invariants:
#   - SCHEMA_VERSION = 2
#   - WAL mode enabled for all connections
#   - Foreign keys enabled for all connections
#   - Row factory set to sqlite3.Row for all connections
#   - Schema version tracked in schema_version table

Path = primitive  # pathlib.Path from standard library

Connection = primitive  # sqlite3.Connection from standard library

class HealthCheckResult:
    """Return type for check_db function - dict with status information"""
    ok: bool                                 # required, True if database is healthy, False otherwise
    error: str = None                        # optional, Error message when ok=False
    version: int = None                      # optional, Current schema version when ok=True
    tables: dict = None                      # optional, Mapping of table names to row counts when ok=True

def get_connection(
    db_path: pathlib.Path,
) -> sqlite3.Connection:
    """
    Open a SQLite connection with WAL mode and foreign keys enabled. Sets row_factory to sqlite3.Row for dict-like access.

    Preconditions:
      - db_path is a valid Path object

    Postconditions:
      - Returns open SQLite connection
      - Connection has journal_mode=WAL
      - Connection has foreign_keys=ON
      - Connection has row_factory=sqlite3.Row

    Errors:
      - database_connection_error (sqlite3.Error): sqlite3.connect() fails due to permissions, invalid path, or disk issues
      - pragma_execution_error (sqlite3.Error): PRAGMA statements fail to execute

    Side effects: Creates database file at db_path if it does not exist, Executes PRAGMA statements on connection
    Idempotent: yes
    """
    ...

def init_db(
    db_path: pathlib.Path,
) -> sqlite3.Connection:
    """
    Create the database and apply the schema if needed. Creates parent directories, checks current schema version, and upgrades schema if current version is less than SCHEMA_VERSION (2). Returns an open connection.

    Preconditions:
      - db_path is a valid Path object

    Postconditions:
      - Database file exists at db_path
      - Parent directories of db_path exist
      - Schema version is SCHEMA_VERSION (2)
      - All tables, triggers, and FTS5 virtual tables are created
      - Returns open connection with WAL mode and foreign keys enabled
      - Changes are committed to database

    Errors:
      - directory_creation_error (OSError): mkdir() fails due to permissions or disk issues
      - schema_query_error (sqlite3.OperationalError): Query to check current schema version fails (caught and handled by setting current=0)
      - schema_execution_error (sqlite3.Error): executescript() or execute() fails during schema creation
      - commit_error (sqlite3.Error): commit() fails due to database lock or disk issues

    Side effects: Creates parent directories for db_path if they don't exist, Creates or updates database schema, Inserts schema version record, Commits transaction to database
    Idempotent: yes
    """
    ...

def check_db(
    db_path: pathlib.Path,
) -> dict:
    """
    Health check that returns database status including schema version and row counts for all tables. Returns dict with ok=False if database doesn't exist or schema not initialized.

    Preconditions:
      - db_path is a valid Path object

    Postconditions:
      - Returns dict with 'ok' key (bool)
      - If ok=False: includes 'error' key with error message
      - If ok=True: includes 'version' key (int) and 'tables' key (dict mapping table names to counts)
      - Connection is closed before returning

    Errors:
      - database_not_found (dict): db_path.exists() returns False
          ok: False
          error: Database not found
      - schema_not_initialized (dict): Query to schema_version table raises OperationalError
          ok: False
          error: Schema not initialized
      - query_execution_error (sqlite3.Error): COUNT queries fail (not caught, will propagate)

    Side effects: Opens and closes database connection, Executes SELECT queries on database
    Idempotent: yes
    """
    ...

# ── REQUIRED EXPORTS ──────────────────────────────────
# Your implementation module MUST export ALL of these names
# with EXACTLY these spellings. Tests import them by name.
# __all__ = ['HealthCheckResult', 'get_connection', 'init_db', 'check_db']
