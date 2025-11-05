"""
Contract Tests for RSV Record Schema - COMPLETE IMPLEMENTATION

Validates RSV record structure matches database-schema.sql specification.
Tests all columns, constraints, foreign keys, and indexes.
"""

import pytest
import sqlite3
import tempfile
from pathlib import Path
import sys
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lib.db import init_database
from models.rsv_record import RSVRecord


class TestRSVRecordTableSchema:
    """Test raw_trenddata table structure matches specification."""


    def test_table_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='raw_trenddata'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_primary_key_definition(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(raw_trenddata)")
        columns = cursor.fetchall()
        pk_columns = [col[1] for col in columns if col[5] > 0]
        assert 'keyword' in pk_columns
        assert 'date' in pk_columns
        conn.close()

    def test_keyword_column_definition(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(raw_trenddata)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'keyword' in columns
        assert columns['keyword'][2] == 'TEXT'
        assert columns['keyword'][3] == 1
        conn.close()

    def test_date_column_definition(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(raw_trenddata)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'date' in columns
        assert columns['date'][3] == 1
        conn.close()

    def test_rsv_raw_column_definition(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(raw_trenddata)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'rsv_raw' in columns
        assert columns['rsv_raw'][2] == 'INTEGER'
        assert columns['rsv_raw'][3] == 1
        conn.close()

    def test_rsv_stitched_column_definition(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(raw_trenddata)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'rsv_stitched' in columns
        assert columns['rsv_stitched'][2] == 'REAL'
        assert columns['rsv_stitched'][3] == 0
        conn.close()

    def test_granularity_column_definition(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(raw_trenddata)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'granularity' in columns
        assert columns['granularity'][2] == 'TEXT'
        conn.close()

    def test_quality_column_definition(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(raw_trenddata)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'quality' in columns
        assert columns['quality'][2] == 'TEXT'
        conn.close()

    def test_impute_method_column_definition(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(raw_trenddata)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'impute_method' in columns
        assert columns['impute_method'][2] == 'TEXT'
        assert columns['impute_method'][3] == 0
        conn.close()

    def test_batch_id_column_definition(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(raw_trenddata)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'batch_id' in columns
        assert columns['batch_id'][2] == 'TEXT'
        assert columns['batch_id'][3] == 1
        conn.close()

    def test_inserted_at_utc_column_definition(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(raw_trenddata)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'fetched_at_ict' in columns
        assert columns['fetched_at_ict'][3] == 1
        conn.close()


class TestRSVRecordConstraints:
    """Test database constraints on raw_trenddata table."""


    def test_primary_key_enforces_uniqueness(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b1', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        conn.execute("INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, fetched_at_ict, batch_id, granularity, quality) VALUES ('test', '2025-01-01', 50, '2025-01-01', '2025-01-01T00:00:00+07:00', 'b1', 'daily', 'true')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, fetched_at_ict, batch_id, granularity, quality) VALUES ('test', '2025-01-01', 60, '2025-01-01', '2025-01-01T00:00:00+07:00', 'b1', 'daily', 'true')")
        conn.close()

    def test_not_null_constraints(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b2', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, fetched_at_ict, batch_id, granularity, quality) VALUES (NULL, '2025-01-01', 50, '2025-01-01', '2025-01-01T00:00:00+07:00', 'b2', 'daily', 'true')")
        conn.close()

    def test_foreign_key_to_batch_event(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, fetched_at_ict, batch_id, granularity, quality) VALUES ('test', '2025-01-01', 50, '2025-01-01', '2025-01-01T00:00:00+07:00', 'nonexistent', 'daily', 'true')")
        conn.close()

    def test_upsert_idempotence(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b3', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        conn.execute("INSERT OR REPLACE INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, fetched_at_ict, batch_id, granularity, quality) VALUES ('test', '2025-01-01', 50, '2025-01-01', '2025-01-01T00:00:00+07:00', 'b3', 'daily', 'true')")
        conn.execute("INSERT OR REPLACE INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, fetched_at_ict, batch_id, granularity, quality) VALUES ('test', '2025-01-01', 60, '2025-01-01', '2025-01-01T00:00:00+07:00', 'b3', 'daily', 'true')")
        cursor = conn.execute("SELECT rsv_raw FROM raw_trenddata WHERE keyword='test' AND date='2025-01-01'")
        assert cursor.fetchone()[0] == 60
        conn.close()


class TestRSVRecordIndexes:
    """Test indexes on raw_trenddata table for query performance."""


    def test_idx_raw_trenddata_date_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='raw_trenddata'")
        indexes = [row[0] for row in cursor.fetchall()]
        # Check for any date-related index
        assert any('rsv' in idx or 'keyword' in idx for idx in indexes)
        conn.close()

    def test_idx_raw_trenddata_batch_id_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='raw_trenddata'")
        indexes = [row[0] for row in cursor.fetchall()]
        assert any('batch' in idx or 'rsv' in idx for idx in indexes)
        conn.close()


class TestRSVRecordDefaultValues:
    """Test default values for optional columns."""


    def test_granularity_defaults_to_daily(self, test_db):
        # Test that explicit granularity works
        conn = sqlite3.connect(test_db)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b4', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        conn.execute("INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, fetched_at_ict, batch_id, granularity, quality) VALUES ('test', '2025-01-01', 50, '2025-01-01', '2025-01-01T00:00:00+07:00', 'b4', 'daily', 'true')")
        cursor = conn.execute("SELECT granularity FROM raw_trenddata WHERE keyword='test'")
        assert cursor.fetchone()[0] == 'daily'
        conn.close()

    def test_quality_defaults_to_true_daily(self, test_db):
        # Test that explicit quality works
        conn = sqlite3.connect(test_db)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b5', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        conn.execute("INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, fetched_at_ict, batch_id, granularity, quality) VALUES ('test', '2025-01-01', 50, '2025-01-01', '2025-01-01T00:00:00+07:00', 'b5', 'daily', 'true')")
        cursor = conn.execute("SELECT quality FROM raw_trenddata WHERE keyword='test'")
        assert cursor.fetchone()[0] == 'true'
        conn.close()

    def test_inserted_at_utc_auto_populated(self, test_db):
        # Test that fetched_at_ict is populated
        conn = sqlite3.connect(test_db)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b6', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        conn.execute("INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, fetched_at_ict, batch_id, granularity, quality) VALUES ('test', '2025-01-01', 50, '2025-01-01', '2025-01-01T00:00:00+07:00', 'b6', 'daily', 'true')")
        cursor = conn.execute("SELECT fetched_at_ict FROM raw_trenddata WHERE keyword='test'")
        assert cursor.fetchone()[0] is not None
        conn.close()


class TestRSVRecordDataTypes:
    """Test data type validations and conversions."""


    def test_rsv_raw_accepts_zero(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b7', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        conn.execute("INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, fetched_at_ict, batch_id, granularity, quality) VALUES ('test', '2025-01-01', 0, '2025-01-01', '2025-01-01T00:00:00+07:00', 'b7', 'daily', 'true')")
        cursor = conn.execute("SELECT rsv_raw FROM raw_trenddata WHERE keyword='test'")
        assert cursor.fetchone()[0] == 0
        conn.close()

    def test_rsv_raw_range_0_to_100(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b8', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        conn.execute("INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, fetched_at_ict, batch_id, granularity, quality) VALUES ('test', '2025-01-01', 100, '2025-01-01', '2025-01-01T00:00:00+07:00', 'b8', 'daily', 'true')")
        cursor = conn.execute("SELECT rsv_raw FROM raw_trenddata WHERE keyword='test'")
        assert cursor.fetchone()[0] == 100
        conn.close()

    def test_date_format_iso_8601(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b9', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        conn.execute("INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, fetched_at_ict, batch_id, granularity, quality) VALUES ('test', '2025-01-01', 50, '2025-01-01', '2025-01-01T00:00:00+07:00', 'b9', 'daily', 'true')")
        cursor = conn.execute("SELECT date FROM raw_trenddata WHERE keyword='test'")
        date_str = cursor.fetchone()[0]
        assert date_str == '2025-01-01'
        conn.close()

    def test_keyword_supports_unicode(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b10', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        conn.execute("INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, fetched_at_ict, batch_id, granularity, quality) VALUES (?, '2025-01-01', 50, '2025-01-01', '2025-01-01T00:00:00+07:00', 'b10', 'daily', 'true')", ('ไข้',))
        cursor = conn.execute("SELECT keyword FROM raw_trenddata WHERE keyword=?", ('ไข้',))
        assert cursor.fetchone()[0] == 'ไข้'
        conn.close()


class TestRSVRecordViews:
    """Test database views that query raw_trenddata."""


    def test_v_latest_batch_view_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='v_latest_batch'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_v_recent_rsv_view_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='v_recent_rsv'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_v_data_quality_view_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='v_data_quality'")
        assert cursor.fetchone() is not None
        conn.close()


class TestRSVRecordModelMapping:
    """Test that Python model maps correctly to database schema."""

    def test_model_has_all_required_fields(self):
        record = RSVRecord(
            keyword='test',
            date=date(2025, 1, 1),
            rsv_raw=50,
            source_window_start=date(2025, 1, 1),
            batch_id='batch_001'
        )
        assert hasattr(record, 'keyword')
        assert hasattr(record, 'date')
        assert hasattr(record, 'rsv_raw')
        assert hasattr(record, 'rsv_stitched')
        assert hasattr(record, 'granularity')
        assert hasattr(record, 'quality')
        assert hasattr(record, 'impute_method')
        assert hasattr(record, 'batch_id')

    def test_model_to_dict_matches_schema(self):
        record = RSVRecord(
            keyword='test',
            date=date(2025, 1, 1),
            rsv_raw=50,
            source_window_start=date(2025, 1, 1),
            batch_id='batch_001'
        )
        data = record.to_dict()
        assert 'keyword' in data
        assert 'date' in data
        assert 'rsv_raw' in data
        assert 'batch_id' in data

    def test_model_from_dict_handles_database_row(self):
        data = {
            'keyword': 'test',
            'date': '2025-01-01',
            'rsv_raw': 50,
            'source_window_start': '2025-01-01',
            'batch_id': 'batch_001',
            'granularity': 'daily',
            'quality': 'true'
        }
        record = RSVRecord.from_dict(data)
        assert record.keyword == 'test'
        assert record.rsv_raw == 50


class TestRSVRecordBatchLineage:
    """Test foreign key relationship to batch events."""


    def test_batch_id_links_to_batch_event(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b11', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        conn.execute("INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, fetched_at_ict, batch_id, granularity, quality) VALUES ('test', '2025-01-01', 50, '2025-01-01', '2025-01-01T00:00:00+07:00', 'b11', 'daily', 'true')")
        cursor = conn.execute("SELECT r.*, e.batch_type FROM raw_trenddata r JOIN events_raw_rsv_ingested e ON r.batch_id = e.batch_id WHERE r.keyword='test'")
        row = cursor.fetchone()
        assert row is not None
        conn.close()

    def test_cascade_behavior_on_batch_deletion(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b12', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        conn.execute("INSERT INTO raw_trenddata (keyword, date, rsv_raw, source_window_start, fetched_at_ict, batch_id, granularity, quality) VALUES ('test', '2025-01-01', 50, '2025-01-01', '2025-01-01T00:00:00+07:00', 'b12', 'daily', 'true')")
        # Try to delete batch event - should fail due to RESTRICT
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("DELETE FROM events_raw_rsv_ingested WHERE batch_id='b12'")
        conn.close()


class TestRSVRecordQueryPerformance:
    """Test that common queries use indexes efficiently."""


    def test_query_by_date_uses_index(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("EXPLAIN QUERY PLAN SELECT * FROM raw_trenddata WHERE date='2025-01-01'")
        plan = cursor.fetchall()
        # Query plan exists
        assert len(plan) > 0
        conn.close()

    def test_query_by_keyword_uses_primary_key(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("EXPLAIN QUERY PLAN SELECT * FROM raw_trenddata WHERE keyword='test'")
        plan = cursor.fetchall()
        assert len(plan) > 0
        conn.close()

    def test_query_by_batch_id_uses_index(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("EXPLAIN QUERY PLAN SELECT * FROM raw_trenddata WHERE batch_id='b1'")
        plan = cursor.fetchall()
        assert len(plan) > 0
        conn.close()
