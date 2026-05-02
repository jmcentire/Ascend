"""
Contract tests for contracts_src_ascend_db_interface

Tests verify the SQLite database interface implementation against its contract,
covering get_connection, init_db, and check_db functions with happy paths,
edge cases, error conditions, and invariants.
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import os

# Import the component under test
from contracts.src_ascend_db.interface import (
    get_connection,
    init_db,
    check_db,
    SCHEMA_VERSION,
    _SCHEMA_SQL
)


class TestGetConnection:
    """Tests for get_connection function"""
    
    def test_get_connection_happy_path(self, tmp_path):
        """get_connection successfully opens a connection with correct configuration"""
        db_path = tmp_path / "test.db"
        
        # Call get_connection
        conn = get_connection(db_path)
        
        # Assert connection is returned
        assert conn is not None
        assert isinstance(conn, sqlite3.Connection)
        
        # Check WAL mode
        cursor = conn.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        assert journal_mode.lower() == "wal"
        
        # Check foreign keys enabled
        cursor = conn.execute("PRAGMA foreign_keys")
        foreign_keys = cursor.fetchone()[0]
        assert foreign_keys == 1
        
        # Check row_factory
        assert conn.row_factory == sqlite3.Row
        
        conn.close()
    
    def test_get_connection_nonexistent_directory(self):
        """get_connection raises error when directory doesn't exist"""
        # Create a path with non-existent parent directory
        db_path = Path("/nonexistent/directory/test.db")
        
        # Attempt to get connection should raise an error
        with pytest.raises((OSError, sqlite3.OperationalError, FileNotFoundError)):
            conn = get_connection(db_path)
    
    def test_get_connection_invalid_path(self):
        """get_connection raises error when path cannot be converted to string"""
        # Create a mock Path object that raises an error on str conversion
        mock_path = Mock(spec=Path)
        mock_path.__str__ = Mock(side_effect=Exception("Cannot convert to string"))
        mock_path.__fspath__ = Mock(side_effect=Exception("Cannot convert to string"))
        
        # Attempt to get connection should raise an error
        with pytest.raises(Exception):
            conn = get_connection(mock_path)


class TestInitDb:
    """Tests for init_db function"""
    
    def test_init_db_happy_path(self, tmp_path):
        """init_db creates database, applies schema, and returns configured connection"""
        db_path = tmp_path / "test.db"
        
        # Call init_db
        conn = init_db(db_path)
        
        # Assert database file exists
        assert db_path.exists()
        
        # Assert parent directories exist
        assert db_path.parent.exists()
        
        # Check schema version
        cursor = conn.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        version = cursor.fetchone()[0]
        assert version == 2
        
        # Check all expected tables exist
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        expected_tables = [
            'schema_version', 'teams', 'members', 'member_flags',
            'team_members', 'meetings', 'meeting_items', 'goals',
            'performance_snapshots', 'coaching_entries', 'schedules'
        ]
        for table in expected_tables:
            assert table in tables, f"Table {table} not found"
        
        # Check connection configuration
        cursor = conn.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0].lower() == "wal"
        
        cursor = conn.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1
        
        assert conn.row_factory == sqlite3.Row
        
        conn.close()
    
    def test_init_db_creates_parent_directories(self, tmp_path):
        """init_db creates parent directories if they don't exist"""
        db_path = tmp_path / "level1" / "level2" / "level3" / "test.db"
        
        # Ensure parent directories don't exist
        assert not db_path.parent.exists()
        
        # Call init_db
        conn = init_db(db_path)
        
        # Assert all parent directories exist
        assert db_path.parent.exists()
        assert db_path.exists()
        
        conn.close()
    
    def test_init_db_idempotent(self, tmp_path):
        """init_db is idempotent - calling twice doesn't break the database"""
        db_path = tmp_path / "test.db"
        
        # Initialize database first time
        conn1 = init_db(db_path)
        cursor = conn1.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        version1 = cursor.fetchone()[0]
        conn1.close()
        
        # Initialize database second time
        conn2 = init_db(db_path)
        cursor = conn2.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        version2 = cursor.fetchone()[0]
        
        # Assert schema version remains 2
        assert version1 == 2
        assert version2 == 2
        
        # Check all tables still exist
        cursor = conn2.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        expected_tables = [
            'schema_version', 'teams', 'members', 'member_flags',
            'team_members', 'meetings', 'meeting_items', 'goals',
            'performance_snapshots', 'coaching_entries', 'schedules'
        ]
        for table in expected_tables:
            assert table in tables
        
        conn2.close()
    
    def test_init_db_permission_error(self, tmp_path):
        """init_db raises permission_error when insufficient permissions"""
        # Create a directory without write permissions
        restricted_dir = tmp_path / "restricted"
        restricted_dir.mkdir()
        os.chmod(restricted_dir, 0o444)  # Read-only
        
        db_path = restricted_dir / "test.db"
        
        try:
            # Attempt to initialize database should raise permission error
            with pytest.raises((PermissionError, OSError)):
                conn = init_db(db_path)
        finally:
            # Restore permissions for cleanup
            os.chmod(restricted_dir, 0o755)


class TestCheckDb:
    """Tests for check_db function"""
    
    def test_check_db_happy_path(self, tmp_path):
        """check_db returns healthy status for initialized database"""
        db_path = tmp_path / "test.db"
        
        # Initialize database
        conn = init_db(db_path)
        conn.close()
        
        # Check database
        result = check_db(db_path)
        
        # Assert ok is True
        assert result['ok'] is True
        
        # Assert version is 2
        assert result['version'] == 2
        
        # Assert tables dict exists
        assert 'tables' in result
        assert isinstance(result['tables'], dict)
        
        # Check all expected tables are present
        expected_tables = [
            'members', 'member_flags', 'teams', 'team_members',
            'meetings', 'meeting_items', 'goals', 'performance_snapshots',
            'coaching_entries', 'schedules'
        ]
        for table in expected_tables:
            assert table in result['tables'], f"Table {table} not in result"
    
    def test_check_db_database_not_found(self, tmp_path):
        """check_db returns error when database doesn't exist"""
        db_path = tmp_path / "nonexistent.db"
        
        # Check database
        result = check_db(db_path)
        
        # Assert ok is False
        assert result['ok'] is False
        
        # Assert error key exists
        assert 'error' in result
        assert isinstance(result['error'], str)
        assert len(result['error']) > 0
    
    def test_check_db_schema_not_initialized(self, tmp_path):
        """check_db returns error when schema is not initialized"""
        db_path = tmp_path / "test.db"
        
        # Create database file without initializing schema
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE dummy (id INTEGER)")
        conn.commit()
        conn.close()
        
        # Check database
        result = check_db(db_path)
        
        # Assert ok is False
        assert result['ok'] is False
        
        # Assert error key exists
        assert 'error' in result
        assert isinstance(result['error'], str)
    
    def test_check_db_closes_connection(self, tmp_path):
        """check_db closes the connection before returning"""
        db_path = tmp_path / "test.db"
        
        # Initialize database
        conn = init_db(db_path)
        conn.close()
        
        # Check database
        result = check_db(db_path)
        
        # The function should have closed the connection
        # We can verify by successfully opening a new connection
        # (if connection wasn't closed, there might be locking issues)
        conn2 = sqlite3.connect(str(db_path))
        cursor = conn2.execute("SELECT 1")
        assert cursor.fetchone()[0] == 1
        conn2.close()


class TestInvariants:
    """Tests for contract invariants"""
    
    def test_schema_version_constant(self):
        """SCHEMA_VERSION constant is 2"""
        assert SCHEMA_VERSION == 2
    
    def test_schema_sql_contains_required_tables(self):
        """_SCHEMA_SQL contains all required table definitions"""
        required_tables = [
            'schema_version', 'teams', 'members', 'member_flags',
            'team_members', 'meetings', 'meeting_items', 'goals',
            'performance_snapshots', 'coaching_entries', 'schedules'
        ]
        
        for table in required_tables:
            assert table in _SCHEMA_SQL, f"Table {table} not in _SCHEMA_SQL"
    
    def test_schema_sql_contains_fts5(self):
        """_SCHEMA_SQL contains FTS5 virtual table for meetings"""
        assert 'meetings_fts' in _SCHEMA_SQL
        assert 'FTS5' in _SCHEMA_SQL or 'fts5' in _SCHEMA_SQL
    
    def test_schema_sql_contains_triggers(self):
        """_SCHEMA_SQL contains triggers for FTS synchronization"""
        assert 'meetings_ai' in _SCHEMA_SQL
        assert 'meetings_ad' in _SCHEMA_SQL
        assert 'meetings_au' in _SCHEMA_SQL
    
    def test_all_connections_use_wal(self, tmp_path):
        """All connections returned use WAL journal mode"""
        db_path = tmp_path / "test.db"
        
        # Test get_connection
        conn = get_connection(db_path)
        cursor = conn.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0].lower() == "wal"
        conn.close()
        
        # Test init_db
        db_path2 = tmp_path / "test2.db"
        conn = init_db(db_path2)
        cursor = conn.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0].lower() == "wal"
        conn.close()
    
    def test_all_connections_have_foreign_keys(self, tmp_path):
        """All connections have foreign key constraints enabled"""
        db_path = tmp_path / "test.db"
        
        # Test get_connection
        conn = get_connection(db_path)
        cursor = conn.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1
        conn.close()
        
        # Test init_db
        db_path2 = tmp_path / "test2.db"
        conn = init_db(db_path2)
        cursor = conn.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1
        conn.close()
    
    def test_all_connections_use_row_factory(self, tmp_path):
        """All connections use sqlite3.Row as row_factory"""
        db_path = tmp_path / "test.db"
        
        # Test get_connection
        conn = get_connection(db_path)
        assert conn.row_factory == sqlite3.Row
        conn.close()
        
        # Test init_db
        db_path2 = tmp_path / "test2.db"
        conn = init_db(db_path2)
        assert conn.row_factory == sqlite3.Row
        conn.close()
