"""
Contract tests for Ascend SQLite Database Interface

Tests verify behavior at boundaries, not internals. Cover happy paths, edge cases,
error cases, and invariants. Mock dependencies where appropriate.
"""

import pytest
import sqlite3
import tempfile
import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import random
import string

# Import the component under test
# Adjust import path as needed based on actual module structure
try:
    from contracts.contracts_src_ascend_db_interface.interface import (
        get_connection,
        init_db,
        check_db,
        SCHEMA_VERSION,
        _SCHEMA_SQL,
    )
except ImportError:
    # Fallback for different module structures
    import contracts_contracts_src_ascend_db_interface_interface as db_interface
    get_connection = db_interface.get_connection
    init_db = db_interface.init_db
    check_db = db_interface.check_db
    SCHEMA_VERSION = getattr(db_interface, 'SCHEMA_VERSION', 2)
    _SCHEMA_SQL = getattr(db_interface, '_SCHEMA_SQL', '')


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_db_path(tmp_path):
    """Provides a temporary database path in an existing directory"""
    return tmp_path / "test.db"


@pytest.fixture
def nonexistent_db_path(tmp_path):
    """Provides a path to a database that doesn't exist"""
    return tmp_path / "nonexistent.db"


@pytest.fixture
def nested_db_path(tmp_path):
    """Provides a database path with non-existent parent directories"""
    return tmp_path / "level1" / "level2" / "level3" / "test.db"


@pytest.fixture
def initialized_db(temp_db_path):
    """Provides a fully initialized database"""
    conn = init_db(temp_db_path)
    conn.close()
    return temp_db_path


@pytest.fixture
def empty_db_file(tmp_path):
    """Creates an empty file (not a valid SQLite database)"""
    db_path = tmp_path / "empty.db"
    db_path.touch()
    return db_path


@pytest.fixture
def db_with_data(initialized_db):
    """Provides a database with some test data"""
    conn = sqlite3.connect(str(initialized_db))
    cursor = conn.cursor()
    
    # Insert test data into various tables
    cursor.execute("INSERT INTO teams (name) VALUES (?)", ("Team Alpha",))
    cursor.execute("INSERT INTO teams (name) VALUES (?)", ("Team Beta",))
    cursor.execute("INSERT INTO members (name, email) VALUES (?, ?)", ("Alice", "alice@example.com"))
    cursor.execute("INSERT INTO members (name, email) VALUES (?, ?)", ("Bob", "bob@example.com"))
    cursor.execute("INSERT INTO goals (title, description) VALUES (?, ?)", ("Goal 1", "Test goal"))
    
    conn.commit()
    conn.close()
    return initialized_db


# ============================================================================
# get_connection Tests
# ============================================================================

def test_get_connection_happy_path(temp_db_path):
    """Successfully opens a connection to a valid database path with all required settings"""
    # Act
    conn = get_connection(temp_db_path)
    
    # Assert - Connection object is returned and is open
    assert conn is not None
    assert isinstance(conn, sqlite3.Connection)
    
    # Assert - WAL journal mode is enabled
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    journal_mode = cursor.fetchone()[0]
    assert journal_mode.lower() == 'wal', f"Expected WAL mode, got {journal_mode}"
    
    # Assert - Foreign keys are enforced
    cursor.execute("PRAGMA foreign_keys")
    foreign_keys = cursor.fetchone()[0]
    assert foreign_keys == 1, "Foreign keys should be enabled"
    
    # Assert - row_factory is sqlite3.Row
    assert conn.row_factory == sqlite3.Row, "row_factory should be sqlite3.Row"
    
    conn.close()


def test_get_connection_creates_db_file(temp_db_path):
    """get_connection creates database file if it doesn't exist"""
    # Arrange
    assert not temp_db_path.exists()
    
    # Act
    conn = get_connection(temp_db_path)
    
    # Assert - Database file exists after connection
    assert temp_db_path.exists(), "Database file should be created"
    
    # Assert - Connection is valid
    assert conn is not None
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    result = cursor.fetchone()[0]
    assert result == 1
    
    conn.close()


def test_get_connection_directory_not_exists(tmp_path):
    """Raises error when parent directory doesn't exist"""
    # Arrange - Path with non-existent parent directory
    db_path = tmp_path / "nonexistent_dir" / "test.db"
    
    # Act & Assert - Exception is raised
    with pytest.raises(Exception) as exc_info:
        get_connection(db_path)
    
    # Assert - Error indicates directory doesn't exist or permission issue
    error_msg = str(exc_info.value).lower()
    assert 'file' in error_msg or 'access' in error_msg or 'directory' in error_msg or 'no such' in error_msg


def test_get_connection_invalid_path():
    """Raises error when path cannot be converted to string"""
    # Arrange - Create a mock object that fails when converted to string
    class InvalidPath:
        def __str__(self):
            raise TypeError("Cannot convert to string")
        
        def __fspath__(self):
            raise TypeError("Cannot convert to path")
    
    invalid_path = InvalidPath()
    
    # Act & Assert - Exception is raised
    with pytest.raises(Exception) as exc_info:
        get_connection(invalid_path)
    
    # Assert - Error indicates invalid path
    assert exc_info.value is not None


def test_get_connection_insufficient_permissions(tmp_path):
    """Raises error when insufficient permissions to access database"""
    # Arrange - Create a directory and make it read-only
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    db_path = readonly_dir / "test.db"
    
    # Make directory read-only (Unix-like systems)
    if os.name != 'nt':  # Skip on Windows
        try:
            os.chmod(readonly_dir, 0o444)
            
            # Act & Assert - Exception is raised
            with pytest.raises(Exception) as exc_info:
                get_connection(db_path)
            
            # Assert - Error indicates permission issue
            error_msg = str(exc_info.value).lower()
            assert 'permission' in error_msg or 'access' in error_msg or 'readonly' in error_msg or 'unable' in error_msg
        finally:
            # Restore permissions for cleanup
            os.chmod(readonly_dir, 0o755)
    else:
        pytest.skip("Permission test skipped on Windows")


# ============================================================================
# init_db Tests
# ============================================================================

def test_init_db_happy_path(temp_db_path):
    """Successfully initializes database with complete schema"""
    # Act
    conn = init_db(temp_db_path)
    
    # Assert - Database file exists
    assert temp_db_path.exists(), "Database file should exist"
    
    # Assert - Connection is returned
    assert conn is not None
    assert isinstance(conn, sqlite3.Connection)
    
    # Assert - Schema version is 2
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    version = cursor.fetchone()[0]
    assert version == 2, f"Schema version should be 2, got {version}"
    
    # Assert - All required tables exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    required_tables = {
        'schema_version', 'teams', 'members', 'member_flags', 'team_members',
        'meetings', 'meeting_items', 'goals', 'performance_snapshots',
        'coaching_entries', 'schedules'
    }
    assert required_tables.issubset(tables), f"Missing tables: {required_tables - tables}"
    
    # Assert - FTS5 virtual table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meetings_fts'")
    assert cursor.fetchone() is not None, "meetings_fts virtual table should exist"
    
    # Assert - Triggers exist
    cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger'")
    triggers = {row[0] for row in cursor.fetchall()}
    required_triggers = {'meetings_ai', 'meetings_ad', 'meetings_au'}
    assert required_triggers.issubset(triggers), f"Missing triggers: {required_triggers - triggers}"
    
    # Assert - WAL mode enabled
    cursor.execute("PRAGMA journal_mode")
    assert cursor.fetchone()[0].lower() == 'wal'
    
    # Assert - Foreign keys enabled
    cursor.execute("PRAGMA foreign_keys")
    assert cursor.fetchone()[0] == 1
    
    conn.close()


def test_init_db_creates_parent_directories(nested_db_path):
    """Creates parent directories if they don't exist"""
    # Arrange
    assert not nested_db_path.parent.exists()
    
    # Act
    conn = init_db(nested_db_path)
    
    # Assert - All parent directories exist
    assert nested_db_path.parent.exists(), "Parent directories should be created"
    assert nested_db_path.parent.parent.exists()
    assert nested_db_path.parent.parent.parent.exists()
    
    # Assert - Database file exists
    assert nested_db_path.exists()
    
    # Assert - Schema is initialized
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM schema_version")
    version = cursor.fetchone()[0]
    assert version == 2
    
    conn.close()


def test_init_db_idempotent(initialized_db):
    """Calling init_db multiple times on same database is safe (idempotent)"""
    # Arrange - Database already initialized
    conn1 = sqlite3.connect(str(initialized_db))
    cursor1 = conn1.cursor()
    cursor1.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    initial_version = cursor1.fetchone()[0]
    
    # Insert some test data to verify it's preserved
    cursor1.execute("INSERT INTO teams (name) VALUES (?)", ("Test Team",))
    conn1.commit()
    cursor1.execute("SELECT COUNT(*) FROM teams")
    initial_count = cursor1.fetchone()[0]
    conn1.close()
    
    # Act - Call init_db again (multiple times)
    conn2 = init_db(initialized_db)
    conn2.close()
    
    conn3 = init_db(initialized_db)
    
    # Assert - Schema version remains 2
    cursor3 = conn3.cursor()
    cursor3.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    final_version = cursor3.fetchone()[0]
    assert final_version == 2, f"Schema version should remain 2, got {final_version}"
    
    # Assert - All tables still exist
    cursor3.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor3.fetchall()}
    required_tables = {
        'schema_version', 'teams', 'members', 'member_flags', 'team_members',
        'meetings', 'meeting_items', 'goals', 'performance_snapshots',
        'coaching_entries', 'schedules'
    }
    assert required_tables.issubset(tables)
    
    # Assert - Data is preserved
    cursor3.execute("SELECT COUNT(*) FROM teams")
    final_count = cursor3.fetchone()[0]
    assert final_count == initial_count, "Data should be preserved"
    
    conn3.close()


def test_init_db_schema_upgrade(temp_db_path):
    """Upgrades schema when current version is less than SCHEMA_VERSION"""
    # Arrange - Create database with version 1
    conn = sqlite3.connect(str(temp_db_path))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
    cursor.execute("INSERT INTO schema_version (version) VALUES (1)")
    cursor.execute("CREATE TABLE teams (id INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()
    
    # Act - Call init_db to upgrade
    conn = init_db(temp_db_path)
    
    # Assert - Schema version is 2 after init
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
    version = cursor.fetchone()[0]
    assert version == 2, f"Schema should be upgraded to version 2, got {version}"
    
    # Assert - All new tables/triggers are created
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    assert 'meetings' in tables
    assert 'meeting_items' in tables
    assert 'goals' in tables
    
    conn.close()


def test_init_db_permission_error(tmp_path):
    """Raises error when insufficient permissions to create database"""
    # Arrange - Create read-only directory (Unix-like systems)
    if os.name != 'nt':
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        os.chmod(readonly_dir, 0o444)
        db_path = readonly_dir / "test.db"
        
        try:
            # Act & Assert - Exception is raised
            with pytest.raises(Exception) as exc_info:
                init_db(db_path)
            
            # Assert - Error indicates permission issue
            error_msg = str(exc_info.value).lower()
            assert 'permission' in error_msg or 'access' in error_msg or 'readonly' in error_msg
        finally:
            os.chmod(readonly_dir, 0o755)
    else:
        pytest.skip("Permission test skipped on Windows")


def test_init_db_sql_error(temp_db_path):
    """Raises error when SQL schema execution fails"""
    # Arrange - Mock _SCHEMA_SQL to contain invalid SQL
    with patch('contracts_contracts_src_ascend_db_interface_interface._SCHEMA_SQL', 'INVALID SQL STATEMENT;;;'):
        # Act & Assert - Exception is raised
        with pytest.raises(Exception) as exc_info:
            init_db(temp_db_path)
        
        # Assert - Error indicates SQL execution failure
        assert exc_info.value is not None


def test_init_db_operational_error(temp_db_path):
    """Raises error when database is locked or corrupted"""
    # Arrange - Create a corrupted database file
    with open(temp_db_path, 'wb') as f:
        # Write invalid SQLite header
        f.write(b'NOT A SQLITE DATABASE FILE\x00' * 10)
    
    # Act & Assert - Exception is raised
    with pytest.raises(Exception) as exc_info:
        init_db(temp_db_path)
    
    # Assert - Error indicates database lock or corruption
    error_msg = str(exc_info.value).lower()
    assert 'database' in error_msg or 'corrupt' in error_msg or 'operational' in error_msg or 'malformed' in error_msg


# ============================================================================
# check_db Tests
# ============================================================================

def test_check_db_happy_path(initialized_db):
    """Successfully checks a healthy initialized database"""
    # Act
    result = check_db(initialized_db)
    
    # Assert - Result has 'ok' key set to True
    assert 'ok' in result
    assert result['ok'] is True, "Health check should succeed"
    
    # Assert - Result has 'version' key with value 2
    assert 'version' in result
    assert result['version'] == 2, f"Version should be 2, got {result['version']}"
    
    # Assert - Result has 'tables' key with dict of table counts
    assert 'tables' in result
    assert isinstance(result['tables'], dict)
    
    # Assert - All expected tables are in 'tables' dict
    expected_tables = {
        'members', 'member_flags', 'teams', 'team_members', 'meetings',
        'meeting_items', 'goals', 'performance_snapshots', 'coaching_entries', 'schedules'
    }
    for table in expected_tables:
        assert table in result['tables'], f"Table {table} should be in result"
        assert isinstance(result['tables'][table], int), f"Count for {table} should be an integer"
    
    # Assert - Connection is closed after check (verify no locks)
    # We can verify this by successfully opening a new connection
    conn = sqlite3.connect(str(initialized_db))
    conn.close()


def test_check_db_database_not_found(tmp_path):
    """Returns error state when database file doesn't exist"""
    # Arrange - Path to non-existent database
    nonexistent = tmp_path / "nonexistent.db"
    
    # Act
    result = check_db(nonexistent)
    
    # Assert - Result has 'ok' key set to False
    assert 'ok' in result
    assert result['ok'] is False, "Health check should fail for non-existent database"
    
    # Assert - Result has 'error' key with description
    assert 'error' in result
    assert isinstance(result['error'], str)
    assert len(result['error']) > 0
    
    # Assert - Error indicates database not found
    error_msg = result['error'].lower()
    assert 'not found' in error_msg or 'does not exist' in error_msg or 'no such' in error_msg


def test_check_db_schema_not_initialized(empty_db_file):
    """Returns error state when schema_version table doesn't exist"""
    # Arrange - Create a valid but empty SQLite database
    conn = sqlite3.connect(str(empty_db_file))
    conn.execute("CREATE TABLE dummy (id INTEGER)")
    conn.commit()
    conn.close()
    
    # Act
    result = check_db(empty_db_file)
    
    # Assert - Result has 'ok' key set to False
    assert 'ok' in result
    assert result['ok'] is False
    
    # Assert - Result has 'error' key
    assert 'error' in result
    
    # Assert - Error indicates schema not initialized
    error_msg = result['error'].lower()
    assert 'schema' in error_msg or 'not initialized' in error_msg or 'version' in error_msg


def test_check_db_sql_error_missing_table(temp_db_path):
    """Returns error when expected table doesn't exist during count query"""
    # Arrange - Create database with schema_version but missing some expected tables
    conn = sqlite3.connect(str(temp_db_path))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
    cursor.execute("INSERT INTO schema_version (version) VALUES (2)")
    cursor.execute("CREATE TABLE teams (id INTEGER PRIMARY KEY)")
    # Intentionally don't create all required tables
    conn.commit()
    conn.close()
    
    # Act
    result = check_db(temp_db_path)
    
    # Assert - Result has 'ok' key set to False
    assert 'ok' in result
    assert result['ok'] is False
    
    # Assert - Result has 'error' key
    assert 'error' in result
    
    # Assert - Error indicates SQL query failure
    error_msg = result['error'].lower()
    assert 'table' in error_msg or 'sql' in error_msg or 'no such' in error_msg


def test_check_db_connection_closed(initialized_db):
    """Verifies connection is properly closed even after errors"""
    # Test successful case
    result1 = check_db(initialized_db)
    assert result1['ok'] is True
    
    # Verify we can immediately open connection (no locks)
    conn = sqlite3.connect(str(initialized_db))
    conn.close()
    
    # Test error case (non-existent database)
    nonexistent = initialized_db.parent / "nonexistent.db"
    result2 = check_db(nonexistent)
    assert result2['ok'] is False
    
    # Test another error case (empty database)
    empty_db = initialized_db.parent / "empty_test.db"
    empty_db.touch()
    result3 = check_db(empty_db)
    assert result3['ok'] is False
    
    # All connections should be closed, no resource leaks
    # This is implicitly tested by the fact that we can continue operations


def test_check_db_with_data(db_with_data):
    """check_db returns accurate table counts with populated tables"""
    # Act
    result = check_db(db_with_data)
    
    # Assert - ok is True
    assert result['ok'] is True
    
    # Assert - tables dict has correct counts for populated tables
    assert 'tables' in result
    assert result['tables']['teams'] == 2, "Should have 2 teams"
    assert result['tables']['members'] == 2, "Should have 2 members"
    assert result['tables']['goals'] == 1, "Should have 1 goal"
    
    # Assert - Empty tables show count of 0
    assert result['tables']['member_flags'] == 0, "member_flags should be empty"
    assert result['tables']['meetings'] == 0, "meetings should be empty"


# ============================================================================
# Invariant Tests
# ============================================================================

def test_invariant_schema_version():
    """SCHEMA_VERSION constant is 2"""
    assert SCHEMA_VERSION == 2, f"SCHEMA_VERSION should be 2, got {SCHEMA_VERSION}"


def test_invariant_all_tables_created(temp_db_path):
    """All required tables are created by init_db"""
    # Arrange & Act - Fresh database initialization
    conn = init_db(temp_db_path)
    cursor = conn.cursor()
    
    # Assert - schema_version table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'")
    assert cursor.fetchone() is not None, "schema_version table should exist"
    
    # Assert - teams table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='teams'")
    assert cursor.fetchone() is not None, "teams table should exist"
    
    # Assert - members table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='members'")
    assert cursor.fetchone() is not None, "members table should exist"
    
    # Assert - member_flags table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='member_flags'")
    assert cursor.fetchone() is not None, "member_flags table should exist"
    
    # Assert - team_members table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='team_members'")
    assert cursor.fetchone() is not None, "team_members table should exist"
    
    # Assert - meetings table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meetings'")
    assert cursor.fetchone() is not None, "meetings table should exist"
    
    # Assert - meeting_items table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meeting_items'")
    assert cursor.fetchone() is not None, "meeting_items table should exist"
    
    # Assert - goals table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='goals'")
    assert cursor.fetchone() is not None, "goals table should exist"
    
    # Assert - performance_snapshots table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='performance_snapshots'")
    assert cursor.fetchone() is not None, "performance_snapshots table should exist"
    
    # Assert - coaching_entries table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='coaching_entries'")
    assert cursor.fetchone() is not None, "coaching_entries table should exist"
    
    # Assert - schedules table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schedules'")
    assert cursor.fetchone() is not None, "schedules table should exist"
    
    # Assert - meetings_fts virtual table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meetings_fts'")
    assert cursor.fetchone() is not None, "meetings_fts virtual table should exist"
    
    conn.close()


def test_invariant_triggers_created(temp_db_path):
    """FTS5 sync triggers are created"""
    # Arrange & Act - Fresh database initialization
    conn = init_db(temp_db_path)
    cursor = conn.cursor()
    
    # Assert - meetings_ai trigger exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='meetings_ai'")
    assert cursor.fetchone() is not None, "meetings_ai trigger should exist"
    
    # Assert - meetings_ad trigger exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='meetings_ad'")
    assert cursor.fetchone() is not None, "meetings_ad trigger should exist"
    
    # Assert - meetings_au trigger exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND name='meetings_au'")
    assert cursor.fetchone() is not None, "meetings_au trigger should exist"
    
    conn.close()


def test_invariant_wal_mode(temp_db_path):
    """All connections use WAL journal mode"""
    # Act
    conn = get_connection(temp_db_path)
    
    # Assert - Connection journal_mode is 'wal'
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    journal_mode = cursor.fetchone()[0]
    assert journal_mode.lower() == 'wal', f"Expected WAL mode, got {journal_mode}"
    
    conn.close()
    
    # Test with init_db as well
    conn2 = init_db(temp_db_path)
    cursor2 = conn2.cursor()
    cursor2.execute("PRAGMA journal_mode")
    journal_mode2 = cursor2.fetchone()[0]
    assert journal_mode2.lower() == 'wal', f"Expected WAL mode from init_db, got {journal_mode2}"
    
    conn2.close()


def test_invariant_foreign_keys(temp_db_path):
    """All connections have foreign key constraints enabled"""
    # Act
    conn = get_connection(temp_db_path)
    
    # Assert - Foreign keys are enabled (PRAGMA foreign_keys returns 1)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys")
    fk_enabled = cursor.fetchone()[0]
    assert fk_enabled == 1, "Foreign keys should be enabled"
    
    conn.close()
    
    # Test with init_db as well
    conn2 = init_db(temp_db_path)
    cursor2 = conn2.cursor()
    cursor2.execute("PRAGMA foreign_keys")
    fk_enabled2 = cursor2.fetchone()[0]
    assert fk_enabled2 == 1, "Foreign keys should be enabled from init_db"
    
    conn2.close()


def test_invariant_row_factory(temp_db_path):
    """All connections use sqlite3.Row as row_factory"""
    # Act
    conn = get_connection(temp_db_path)
    
    # Assert - Connection row_factory is sqlite3.Row
    assert conn.row_factory == sqlite3.Row, "row_factory should be sqlite3.Row"
    
    conn.close()
    
    # Test with init_db as well
    conn2 = init_db(temp_db_path)
    assert conn2.row_factory == sqlite3.Row, "row_factory from init_db should be sqlite3.Row"
    
    conn2.close()


def test_check_db_expected_tables(initialized_db):
    """check_db expects specific tables in its verification"""
    # Arrange - Initialized database
    
    # Act
    result = check_db(initialized_db)
    
    # Assert - tables dict includes all expected tables
    assert result['ok'] is True
    expected_tables = {
        'members', 'member_flags', 'teams', 'team_members', 'meetings',
        'meeting_items', 'goals', 'performance_snapshots', 'coaching_entries', 'schedules'
    }
    
    for table in expected_tables:
        assert table in result['tables'], f"Expected table {table} in check_db result"
        assert isinstance(result['tables'][table], int), f"Count for {table} should be integer"


# ============================================================================
# Additional Edge Cases and Integration Tests
# ============================================================================

def test_connection_resource_cleanup(temp_db_path):
    """Verify connections are properly managed and don't leak"""
    # Open and close multiple connections
    for _ in range(10):
        conn = get_connection(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        conn.close()
    
    # Should still be able to open connection
    final_conn = get_connection(temp_db_path)
    assert final_conn is not None
    final_conn.close()


def test_init_db_multiple_rapid_calls(temp_db_path):
    """Test rapid repeated calls to init_db (stress test for idempotency)"""
    # Call init_db multiple times in succession
    for i in range(5):
        conn = init_db(temp_db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        version = cursor.fetchone()[0]
        assert version == 2, f"Version should be 2 on iteration {i}"
        conn.close()


def test_check_db_corrupted_schema_version(temp_db_path):
    """Test check_db with corrupted schema_version data"""
    # Arrange - Create database with invalid schema_version entry
    conn = sqlite3.connect(str(temp_db_path))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE schema_version (version INTEGER PRIMARY KEY)")
    cursor.execute("INSERT INTO schema_version (version) VALUES (999)")  # Invalid version
    cursor.execute("CREATE TABLE teams (id INTEGER PRIMARY KEY)")
    conn.commit()
    conn.close()
    
    # Act - check_db should still work but might report unexpected version
    result = check_db(temp_db_path)
    
    # The behavior depends on implementation - it may succeed with wrong version
    # or fail due to missing tables
    assert 'ok' in result
    if result['ok']:
        assert 'version' in result


def test_get_connection_existing_database(initialized_db):
    """Test get_connection on an already initialized database"""
    # Act
    conn = get_connection(initialized_db)
    
    # Assert - Can query existing tables
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cursor.fetchall()}
    
    assert 'teams' in tables
    assert 'members' in tables
    
    conn.close()


def test_row_factory_functionality(initialized_db):
    """Test that sqlite3.Row factory works correctly"""
    # Arrange
    conn = get_connection(initialized_db)
    cursor = conn.cursor()
    
    # Insert test data
    cursor.execute("INSERT INTO teams (name) VALUES (?)", ("Test Team",))
    conn.commit()
    
    # Act - Query with Row factory
    cursor.execute("SELECT id, name FROM teams WHERE name = ?", ("Test Team",))
    row = cursor.fetchone()
    
    # Assert - Can access by column name (dict-like)
    assert row['name'] == "Test Team"
    assert 'id' in row.keys()
    
    # Assert - Can also access by index
    assert row[1] == "Test Team"
    
    conn.close()


def test_init_db_preserves_data_on_reinitialization(temp_db_path):
    """Verify that reinitializing doesn't destroy existing data"""
    # Arrange - Initialize and add data
    conn1 = init_db(temp_db_path)
    cursor1 = conn1.cursor()
    cursor1.execute("INSERT INTO teams (name) VALUES (?)", ("Persistent Team",))
    conn1.commit()
    conn1.close()
    
    # Act - Reinitialize
    conn2 = init_db(temp_db_path)
    cursor2 = conn2.cursor()
    
    # Assert - Data still exists
    cursor2.execute("SELECT name FROM teams WHERE name = ?", ("Persistent Team",))
    result = cursor2.fetchone()
    assert result is not None
    assert result[0] == "Persistent Team"
    
    conn2.close()


def test_check_db_empty_tables(initialized_db):
    """Verify check_db correctly reports counts for empty tables"""
    # Act
    result = check_db(initialized_db)
    
    # Assert
    assert result['ok'] is True
    
    # All tables should exist with 0 count
    for table in ['members', 'teams', 'meetings', 'goals']:
        assert table in result['tables']
        assert result['tables'][table] == 0, f"Table {table} should have 0 rows"


def test_foreign_key_enforcement(initialized_db):
    """Verify that foreign key constraints are actually enforced"""
    # Arrange
    conn = get_connection(initialized_db)
    cursor = conn.cursor()
    
    # Try to insert a team_member without a valid team_id
    # This should fail if foreign keys are enforced
    with pytest.raises(sqlite3.IntegrityError):
        cursor.execute("INSERT INTO team_members (team_id, member_id) VALUES (?, ?)", (9999, 9999))
    
    conn.close()


def test_wal_mode_persistence(temp_db_path):
    """Verify WAL mode persists across connection cycles"""
    # Arrange
    conn1 = init_db(temp_db_path)
    conn1.close()
    
    # Act - Open new connection
    conn2 = sqlite3.connect(str(temp_db_path))
    cursor = conn2.cursor()
    cursor.execute("PRAGMA journal_mode")
    mode = cursor.fetchone()[0]
    
    # Assert - WAL mode should persist
    assert mode.lower() == 'wal', "WAL mode should persist across connections"
    
    conn2.close()


def test_random_path_characters(tmp_path):
    """Test database creation with various valid path characters"""
    # Generate random valid filename
    valid_chars = string.ascii_letters + string.digits + "_-"
    random_name = ''.join(random.choice(valid_chars) for _ in range(20)) + ".db"
    db_path = tmp_path / random_name
    
    # Act
    conn = init_db(db_path)
    
    # Assert
    assert db_path.exists()
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM schema_version")
    assert cursor.fetchone()[0] == 2
    
    conn.close()


def test_check_db_after_manual_table_drop(initialized_db):
    """Test check_db behavior when tables are manually dropped"""
    # Arrange - Drop a required table
    conn = sqlite3.connect(str(initialized_db))
    cursor = conn.cursor()
    cursor.execute("DROP TABLE members")
    conn.commit()
    conn.close()
    
    # Act
    result = check_db(initialized_db)
    
    # Assert - Should report error due to missing table
    assert result['ok'] is False
    assert 'error' in result
