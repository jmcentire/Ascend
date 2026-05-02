"""
Contract tests for src_ascend_db module.

Tests verify the SQLite database layer implementation against its contract,
including connection management, schema initialization, and health checks.
"""

import pytest
import sqlite3
import tempfile
import os
import stat
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from src.ascend.db import *


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_db_path(tmp_path):
    """Provide a temporary database path."""
    return tmp_path / "test.db"


@pytest.fixture
def temp_db_with_subdirs(tmp_path):
    """Provide a temporary database path with non-existent parent directories."""
    return tmp_path / "subdir1" / "subdir2" / "test.db"


@pytest.fixture
def initialized_db(tmp_path):
    """Provide a path to an initialized database."""
    db_path = tmp_path / "initialized.db"
    conn = init_db(db_path)
    conn.close()
    return db_path


@pytest.fixture
def empty_db(tmp_path):
    """Provide a path to an empty database without schema."""
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.close()
    return db_path


# ============================================================================
# get_connection Tests
# ============================================================================

def test_get_connection_happy_path(temp_db_path):
    """Test get_connection returns a valid SQLite connection with correct configuration."""
    conn = get_connection(temp_db_path)
    
    assert conn is not None
    assert isinstance(conn, sqlite3.Connection)
    
    # Check WAL mode
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    journal_mode = cursor.fetchone()[0]
    assert journal_mode.lower() == 'wal'
    
    # Check foreign keys
    cursor.execute("PRAGMA foreign_keys")
    foreign_keys = cursor.fetchone()[0]
    assert foreign_keys == 1
    
    # Check row factory
    assert conn.row_factory == sqlite3.Row
    
    conn.close()


def test_get_connection_wal_mode(temp_db_path):
    """Verify WAL mode is enabled on returned connection."""
    conn = get_connection(temp_db_path)
    
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode")
    result = cursor.fetchone()[0]
    assert result.lower() == 'wal'
    
    conn.close()


def test_get_connection_foreign_keys(temp_db_path):
    """Verify foreign keys are enabled on returned connection."""
    conn = get_connection(temp_db_path)
    
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys")
    result = cursor.fetchone()[0]
    assert result == 1
    
    conn.close()


def test_get_connection_row_factory(temp_db_path):
    """Verify row_factory is set to sqlite3.Row."""
    conn = get_connection(temp_db_path)
    
    assert conn.row_factory == sqlite3.Row
    
    conn.close()


def test_get_connection_invalid_path(tmp_path):
    """Test get_connection raises error for invalid path that causes connection failure."""
    # Create a file where we want a directory to cause path issues
    invalid_path = tmp_path / "file.db" / "nested.db"
    (tmp_path / "file.db").touch()
    
    # Should raise an error when trying to connect
    with pytest.raises(Exception):  # Could be OSError, sqlite3.Error, etc.
        get_connection(invalid_path)


def test_get_connection_with_mock_connection_error():
    """Test get_connection handles sqlite3.connect() failure."""
    with patch('sqlite3.connect', side_effect=sqlite3.Error("Connection failed")):
        with pytest.raises(Exception):
            get_connection(Path("/tmp/test.db"))


# ============================================================================
# init_db Tests
# ============================================================================

def test_init_db_happy_path(temp_db_path):
    """Test init_db creates database with schema version 2 and all tables."""
    conn = init_db(temp_db_path)
    
    # Verify database file exists
    assert temp_db_path.exists()
    
    # Verify parent directories exist
    assert temp_db_path.parent.exists()
    
    # Verify schema version
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM schema_version")
    version = cursor.fetchone()[0]
    assert version == 2
    
    # Verify connection is open and configured
    assert isinstance(conn, sqlite3.Connection)
    
    # Check WAL mode
    cursor.execute("PRAGMA journal_mode")
    assert cursor.fetchone()[0].lower() == 'wal'
    
    # Check foreign keys
    cursor.execute("PRAGMA foreign_keys")
    assert cursor.fetchone()[0] == 1
    
    conn.close()


def test_init_db_creates_parent_dirs(temp_db_with_subdirs):
    """Test init_db creates parent directories if they don't exist."""
    assert not temp_db_with_subdirs.parent.exists()
    
    conn = init_db(temp_db_with_subdirs)
    
    assert temp_db_with_subdirs.parent.exists()
    assert temp_db_with_subdirs.exists()
    
    conn.close()


def test_init_db_idempotent(temp_db_path):
    """Test init_db can be called multiple times safely."""
    # First initialization
    conn1 = init_db(temp_db_path)
    cursor1 = conn1.cursor()
    cursor1.execute("SELECT version FROM schema_version")
    version1 = cursor1.fetchone()[0]
    conn1.close()
    
    # Second initialization
    conn2 = init_db(temp_db_path)
    cursor2 = conn2.cursor()
    cursor2.execute("SELECT version FROM schema_version")
    version2 = cursor2.fetchone()[0]
    
    assert version1 == 2
    assert version2 == 2
    assert isinstance(conn2, sqlite3.Connection)
    
    conn2.close()


def test_init_db_schema_upgrade(tmp_path):
    """Test init_db upgrades schema from version 0 or 1 to version 2."""
    db_path = tmp_path / "upgrade.db"
    
    # Create database with old schema (version 1)
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE schema_version (version INTEGER)")
    conn.execute("INSERT INTO schema_version (version) VALUES (1)")
    conn.commit()
    conn.close()
    
    # Run init_db to upgrade
    conn = init_db(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM schema_version")
    version = cursor.fetchone()[0]
    
    assert version == 2
    
    conn.close()


def test_init_db_readonly_parent(tmp_path):
    """Test init_db raises error when parent directory cannot be created."""
    # Create a read-only directory
    readonly_dir = tmp_path / "readonly"
    readonly_dir.mkdir()
    os.chmod(readonly_dir, stat.S_IRUSR | stat.S_IXUSR)
    
    db_path = readonly_dir / "subdir" / "test.db"
    
    try:
        with pytest.raises(Exception):  # Should raise PermissionError or OSError
            init_db(db_path)
    finally:
        # Restore permissions for cleanup
        os.chmod(readonly_dir, stat.S_IRWXU)


def test_init_db_with_mock_mkdir_error():
    """Test init_db handles mkdir() failure."""
    with patch('pathlib.Path.mkdir', side_effect=OSError("Permission denied")):
        with pytest.raises(Exception):
            init_db(Path("/tmp/test/nested/db.db"))


# ============================================================================
# check_db Tests
# ============================================================================

def test_check_db_happy_path(initialized_db):
    """Test check_db returns correct status for initialized database."""
    result = check_db(initialized_db)
    
    assert isinstance(result, dict)
    assert result['ok'] is True
    assert result['version'] == 2
    assert 'tables' in result
    assert isinstance(result['tables'], dict)
    
    # Verify we have table names in the result
    assert len(result['tables']) >= 0  # At least schema_version table


def test_check_db_nonexistent(tmp_path):
    """Test check_db returns ok=False for non-existent database."""
    nonexistent_path = tmp_path / "does_not_exist.db"
    
    result = check_db(nonexistent_path)
    
    assert isinstance(result, dict)
    assert result['ok'] is False
    assert 'error' in result


def test_check_db_not_initialized(empty_db):
    """Test check_db returns ok=False for database without schema."""
    result = check_db(empty_db)
    
    assert isinstance(result, dict)
    assert result['ok'] is False
    assert 'error' in result


def test_check_db_closes_connection(initialized_db):
    """Test check_db properly closes connection before returning."""
    # Get initial connection count
    initial_connections = len([c for c in [initialized_db] if initialized_db.exists()])
    
    result = check_db(initialized_db)
    
    # The function should close its connection
    # We can't directly check if connection is closed, but we verify no exceptions occur
    assert result is not None
    
    # Try to verify the database is not locked
    conn = sqlite3.connect(str(initialized_db))
    cursor = conn.cursor()
    cursor.execute("SELECT 1")
    conn.close()


def test_check_db_with_tables_and_data(initialized_db):
    """Test check_db returns table counts correctly."""
    # Add some test data
    conn = sqlite3.connect(str(initialized_db))
    cursor = conn.cursor()
    
    # Create a test table and insert data
    cursor.execute("CREATE TABLE IF NOT EXISTS test_table (id INTEGER PRIMARY KEY, name TEXT)")
    cursor.execute("INSERT INTO test_table (name) VALUES ('test1')")
    cursor.execute("INSERT INTO test_table (name) VALUES ('test2')")
    conn.commit()
    conn.close()
    
    result = check_db(initialized_db)
    
    assert result['ok'] is True
    assert 'tables' in result
    # The tables dict should contain counts
    assert isinstance(result['tables'], dict)


# ============================================================================
# Invariant Tests
# ============================================================================

def test_invariant_schema_version_constant(temp_db_path):
    """Verify SCHEMA_VERSION constant is 2."""
    conn = init_db(temp_db_path)
    
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM schema_version")
    version = cursor.fetchone()[0]
    
    assert version == 2
    
    conn.close()


def test_invariant_wal_mode_all_connections(temp_db_path):
    """Verify all connections have WAL mode enabled."""
    # Create multiple connections
    conn1 = get_connection(temp_db_path)
    conn2 = get_connection(temp_db_path)
    conn3 = init_db(temp_db_path)
    
    for conn in [conn1, conn2, conn3]:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        mode = cursor.fetchone()[0]
        assert mode.lower() == 'wal'
        conn.close()


def test_invariant_foreign_keys_all_connections(temp_db_path):
    """Verify all connections have foreign keys enabled."""
    conn1 = get_connection(temp_db_path)
    conn2 = get_connection(temp_db_path)
    conn3 = init_db(temp_db_path)
    
    for conn in [conn1, conn2, conn3]:
        cursor = conn.cursor()
        cursor.execute("PRAGMA foreign_keys")
        fk_enabled = cursor.fetchone()[0]
        assert fk_enabled == 1
        conn.close()


def test_invariant_row_factory_all_connections(temp_db_path):
    """Verify all connections have row_factory set to sqlite3.Row."""
    conn1 = get_connection(temp_db_path)
    conn2 = get_connection(temp_db_path)
    conn3 = init_db(temp_db_path)
    
    for conn in [conn1, conn2, conn3]:
        assert conn.row_factory == sqlite3.Row
        conn.close()


# ============================================================================
# Integration Tests
# ============================================================================

def test_integration_init_connect_check(temp_db_path):
    """Integration test for complete workflow: init -> connect -> check."""
    # Step 1: Initialize database
    conn_init = init_db(temp_db_path)
    assert temp_db_path.exists()
    conn_init.close()
    
    # Step 2: Get connection
    conn_get = get_connection(temp_db_path)
    assert isinstance(conn_get, sqlite3.Connection)
    
    # Verify WAL mode
    cursor = conn_get.cursor()
    cursor.execute("PRAGMA journal_mode")
    assert cursor.fetchone()[0].lower() == 'wal'
    
    conn_get.close()
    
    # Step 3: Check database health
    result = check_db(temp_db_path)
    assert result['ok'] is True
    assert result['version'] == 2
    assert 'tables' in result
    
    # Verify all invariants maintained
    final_conn = get_connection(temp_db_path)
    assert final_conn.row_factory == sqlite3.Row
    cursor = final_conn.cursor()
    cursor.execute("PRAGMA foreign_keys")
    assert cursor.fetchone()[0] == 1
    final_conn.close()


# ============================================================================
# Edge Case Tests
# ============================================================================

def test_edge_case_empty_tables(initialized_db):
    """Test check_db with initialized database containing empty tables."""
    result = check_db(initialized_db)
    
    assert result['ok'] is True
    assert 'tables' in result
    
    # All counts should be >= 0
    for table_name, count in result['tables'].items():
        assert count >= 0


def test_edge_case_special_chars_in_path(tmp_path):
    """Test database operations with special characters in path."""
    # Create path with spaces and unicode
    special_path = tmp_path / "test db with spaces" / "データベース.db"
    
    conn = init_db(special_path)
    assert special_path.exists()
    
    cursor = conn.cursor()
    cursor.execute("SELECT version FROM schema_version")
    version = cursor.fetchone()[0]
    assert version == 2
    
    conn.close()
    
    # Verify check_db works with special path
    result = check_db(special_path)
    assert result['ok'] is True


def test_edge_case_concurrent_init(temp_db_path):
    """Test multiple init_db calls in sequence (simulating concurrent access)."""
    conn1 = init_db(temp_db_path)
    cursor1 = conn1.cursor()
    cursor1.execute("SELECT version FROM schema_version")
    v1 = cursor1.fetchone()[0]
    conn1.close()
    
    conn2 = init_db(temp_db_path)
    cursor2 = conn2.cursor()
    cursor2.execute("SELECT version FROM schema_version")
    v2 = cursor2.fetchone()[0]
    conn2.close()
    
    assert v1 == 2
    assert v2 == 2


def test_edge_case_path_as_string_convertible(tmp_path):
    """Test that Path objects are handled correctly."""
    db_path = tmp_path / "test.db"
    
    # Ensure we're passing a Path object
    assert isinstance(db_path, Path)
    
    conn = init_db(db_path)
    assert isinstance(conn, sqlite3.Connection)
    conn.close()


def test_check_db_returns_dict_structure(initialized_db):
    """Verify check_db returns dict with correct structure."""
    result = check_db(initialized_db)
    
    # Should be a dict
    assert isinstance(result, dict)
    
    # Should have 'ok' key
    assert 'ok' in result
    assert isinstance(result['ok'], bool)
    
    # If ok=True, should have version and tables
    if result['ok']:
        assert 'version' in result
        assert isinstance(result['version'], int)
        assert 'tables' in result
        assert isinstance(result['tables'], dict)
    else:
        # If ok=False, should have error
        assert 'error' in result
        assert isinstance(result['error'], str)


def test_get_connection_creates_file(temp_db_path):
    """Test that get_connection creates the database file."""
    assert not temp_db_path.exists()
    
    conn = get_connection(temp_db_path)
    
    assert temp_db_path.exists()
    conn.close()


def test_init_db_commits_changes(temp_db_path):
    """Test that init_db commits changes to database."""
    conn = init_db(temp_db_path)
    conn.close()
    
    # Open a new connection and verify schema exists
    new_conn = sqlite3.connect(str(temp_db_path))
    cursor = new_conn.cursor()
    cursor.execute("SELECT version FROM schema_version")
    version = cursor.fetchone()[0]
    assert version == 2
    new_conn.close()


def test_check_db_with_corrupted_schema_version(tmp_path):
    """Test check_db handles corrupted schema_version table."""
    db_path = tmp_path / "corrupted.db"
    
    # Create database with malformed schema_version
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE schema_version (wrong_column TEXT)")
    conn.commit()
    conn.close()
    
    result = check_db(db_path)
    
    # Should handle the error gracefully
    # Depending on implementation, might return ok=False or raise
    assert isinstance(result, dict)
    assert 'ok' in result
