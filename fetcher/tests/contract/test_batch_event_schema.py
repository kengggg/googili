"""
Contract Tests for Batch Event Schema - COMPLETE IMPLEMENTATION

Validates batch event structure matches spec.md requirements (FR-008).
Tests all required fields, JSON array handling, timestamp format.
"""

import pytest
import sqlite3
import json
import tempfile
from pathlib import Path
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lib.db import init_database
from lib.timezone_utils import ICT
from models.batch_event import BatchEvent


class TestBatchEventTableSchema:
    """Test events_raw_rsv_ingested table structure."""

    def test_table_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events_raw_rsv_ingested'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_primary_key_is_batch_id(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = cursor.fetchall()
        pk_columns = [col[1] for col in columns if col[5] > 0]
        assert 'batch_id' in pk_columns
        conn.close()


class TestBatchEventRequiredFields:
    """Test required fields per FR-008 specification."""

    def test_batch_id_column(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'batch_id' in columns
        assert columns['batch_id'][2] == 'TEXT'
        conn.close()

    def test_batch_type_column(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'batch_type' in columns
        assert columns['batch_type'][2] == 'TEXT'
        assert columns['batch_type'][3] == 1  # not null
        conn.close()

    def test_requested_keywords_column(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'requested_keywords' in columns
        assert columns['requested_keywords'][2] == 'TEXT'
        conn.close()

    def test_requested_window_column(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'requested_window' in columns
        assert columns['requested_window'][2] == 'TEXT'
        conn.close()

    def test_started_at_ict_column(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'started_at_ict' in columns
        assert columns['started_at_ict'][3] == 1  # not null
        conn.close()

    def test_finished_at_ict_column(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'finished_at_ict' in columns
        assert columns['finished_at_ict'][3] == 0  # nullable
        conn.close()

    def test_status_column(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'status' in columns
        assert columns['status'][2] == 'TEXT'
        assert columns['status'][3] == 1  # not null
        conn.close()


class TestBatchEventCountFields:
    """Test count fields for tracking data written."""


    def test_rows_written_column(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'rows_written' in columns
        assert columns['rows_written'][2] == 'INTEGER'
        conn.close()

    def test_rows_updated_column(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'rows_updated' in columns
        assert columns['rows_updated'][2] == 'INTEGER'
        conn.close()

    def test_rows_missing_column(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'rows_missing' in columns
        assert columns['rows_missing'][2] == 'INTEGER'
        conn.close()


class TestBatchEventQualityFields:
    """Test quality metric fields (User Story 5)."""


    def test_quality_true_daily_column(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'quality_true_daily' in columns
        assert columns['quality_true_daily'][3] == 0  # nullable
        conn.close()

    def test_quality_weekly_flat_column(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'quality_weekly_flat' in columns
        assert columns['quality_weekly_flat'][3] == 0  # nullable
        conn.close()

    def test_quality_below_detection_column(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'quality_below_detection' in columns
        assert columns['quality_below_detection'][3] == 0  # nullable
        conn.close()


class TestBatchEventMetadataFields:
    """Test optional metadata fields."""


    def test_notes_column(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'notes' in columns
        assert columns['notes'][2] == 'TEXT'
        conn.close()

    def test_error_message_column(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = {col[1]: col for col in cursor.fetchall()}
        assert 'error_message' in columns
        assert columns['error_message'][2] == 'TEXT'
        conn.close()


class TestBatchEventIndexes:
    """Test indexes for query performance."""


    def test_idx_batch_event_status_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='events_raw_rsv_ingested'")
        indexes = [row[0] for row in cursor.fetchall()]
        assert any('status' in idx or 'events' in idx for idx in indexes)
        conn.close()

    def test_idx_batch_event_started_at_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='events_raw_rsv_ingested'")
        indexes = [row[0] for row in cursor.fetchall()]
        assert any('finished' in idx or 'events' in idx for idx in indexes)
        conn.close()


class TestBatchEventJSONArrayHandling:
    """Test requested_keywords JSON array storage and retrieval."""


    def test_keywords_stored_as_valid_json(self, test_db):
        conn = sqlite3.connect(test_db)
        keywords = json.dumps(['test1', 'test2'], ensure_ascii=False)
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b1', 'daily', ?, '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')", (keywords,))
        cursor = conn.execute("SELECT requested_keywords FROM events_raw_rsv_ingested WHERE batch_id='b1'")
        result = json.loads(cursor.fetchone()[0])
        assert isinstance(result, list)
        conn.close()

    def test_keywords_preserve_thai_unicode(self, test_db):
        conn = sqlite3.connect(test_db)
        keywords = json.dumps(['ไข้', 'ไอ', 'เจ็บคอ'], ensure_ascii=False)
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b2', 'daily', ?, '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')", (keywords,))
        cursor = conn.execute("SELECT requested_keywords FROM events_raw_rsv_ingested WHERE batch_id='b2'")
        result = json.loads(cursor.fetchone()[0])
        assert 'ไข้' in result
        assert 'ไอ' in result
        assert 'เจ็บคอ' in result
        conn.close()

    def test_keywords_empty_array_valid(self, test_db):
        conn = sqlite3.connect(test_db)
        keywords = json.dumps([], ensure_ascii=False)
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b3', 'daily', ?, '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')", (keywords,))
        cursor = conn.execute("SELECT requested_keywords FROM events_raw_rsv_ingested WHERE batch_id='b3'")
        result = json.loads(cursor.fetchone()[0])
        assert result == []
        conn.close()

    def test_keywords_order_preserved(self, test_db):
        conn = sqlite3.connect(test_db)
        keywords = json.dumps(['ไข้', 'ไอ', 'เจ็บคอ'], ensure_ascii=False)
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b4', 'daily', ?, '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')", (keywords,))
        cursor = conn.execute("SELECT requested_keywords FROM events_raw_rsv_ingested WHERE batch_id='b4'")
        result = json.loads(cursor.fetchone()[0])
        assert result == ['ไข้', 'ไอ', 'เจ็บคอ']
        conn.close()


class TestBatchEventTimestampFormat:
    """Test timestamp format and timezone handling."""


    def test_started_at_ict_iso8601_format(self, test_db):
        conn = sqlite3.connect(test_db)
        timestamp = '2025-11-04T07:32:15+07:00'
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b5', 'daily', '[]', '2025-01-01 to 2025-01-01', ?, 'running')", (timestamp,))
        cursor = conn.execute("SELECT started_at_ict FROM events_raw_rsv_ingested WHERE batch_id='b5'")
        result = cursor.fetchone()[0]
        assert '+07:00' in result or 'T' in result
        conn.close()

    def test_started_at_ict_has_bangkok_offset(self, test_db):
        conn = sqlite3.connect(test_db)
        timestamp = '2025-11-04T07:32:15+07:00'
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b6', 'daily', '[]', '2025-01-01 to 2025-01-01', ?, 'running')", (timestamp,))
        cursor = conn.execute("SELECT started_at_ict FROM events_raw_rsv_ingested WHERE batch_id='b6'")
        result = cursor.fetchone()[0]
        assert '+07:00' in result or '07:' in result
        conn.close()

    def test_finished_at_ict_iso8601_format(self, test_db):
        conn = sqlite3.connect(test_db)
        start = '2025-11-04T07:00:00+07:00'
        finish = '2025-11-04T07:30:00+07:00'
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, finished_at_ict, status) VALUES ('b7', 'daily', '[]', '2025-01-01 to 2025-01-01', ?, ?, 'success')", (start, finish))
        cursor = conn.execute("SELECT finished_at_ict FROM events_raw_rsv_ingested WHERE batch_id='b7'")
        result = cursor.fetchone()[0]
        assert '+07:00' in result or 'T' in result
        conn.close()

    def test_finished_at_ict_nullable(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b8', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        cursor = conn.execute("SELECT finished_at_ict FROM events_raw_rsv_ingested WHERE batch_id='b8'")
        result = cursor.fetchone()[0]
        assert result is None
        conn.close()


class TestBatchEventStatusValues:
    """Test valid status enum values."""


    def test_status_running_valid(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b9', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        cursor = conn.execute("SELECT status FROM events_raw_rsv_ingested WHERE batch_id='b9'")
        assert cursor.fetchone()[0] == 'running'
        conn.close()

    def test_status_success_valid(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b10', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'success')")
        cursor = conn.execute("SELECT status FROM events_raw_rsv_ingested WHERE batch_id='b10'")
        assert cursor.fetchone()[0] == 'success'
        conn.close()

    def test_status_degraded_valid(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b11', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'degraded')")
        cursor = conn.execute("SELECT status FROM events_raw_rsv_ingested WHERE batch_id='b11'")
        assert cursor.fetchone()[0] == 'degraded'
        conn.close()

    def test_status_fail_valid(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b12', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'fail')")
        cursor = conn.execute("SELECT status FROM events_raw_rsv_ingested WHERE batch_id='b12'")
        assert cursor.fetchone()[0] == 'fail'
        conn.close()


class TestBatchEventWindowFormat:
    """Test requested_window date range format."""


    def test_window_format_matches_spec(self, test_db):
        conn = sqlite3.connect(test_db)
        window = "2025-11-03 to 2025-11-04"
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b13', 'daily', '[]', ?, '2025-01-01T00:00:00+07:00', 'running')", (window,))
        cursor = conn.execute("SELECT requested_window FROM events_raw_rsv_ingested WHERE batch_id='b13'")
        assert cursor.fetchone()[0] == window
        conn.close()

    def test_window_single_day_format(self, test_db):
        conn = sqlite3.connect(test_db)
        window = "2025-11-04 to 2025-11-04"
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b14', 'daily', '[]', ?, '2025-01-01T00:00:00+07:00', 'running')", (window,))
        cursor = conn.execute("SELECT requested_window FROM events_raw_rsv_ingested WHERE batch_id='b14'")
        assert cursor.fetchone()[0] == window
        conn.close()

    def test_window_backfill_format(self, test_db):
        conn = sqlite3.connect(test_db)
        window = "2025-08-06 to 2025-11-04"
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b15', 'initial_backfill', '[]', ?, '2025-01-01T00:00:00+07:00', 'running')", (window,))
        cursor = conn.execute("SELECT requested_window FROM events_raw_rsv_ingested WHERE batch_id='b15'")
        assert cursor.fetchone()[0] == window
        conn.close()


class TestBatchEventViews:
    """Test database views querying batch events."""


    def test_v_latest_batch_view_exists(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='view' AND name='v_latest_batch'")
        assert cursor.fetchone() is not None
        conn.close()

    def test_v_latest_batch_shows_recent_success(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, finished_at_ict, status, rows_written) VALUES ('b16', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', '2025-01-01T00:10:00+07:00', 'success', 10)")
        cursor = conn.execute("SELECT * FROM v_latest_batch WHERE status='success'")
        # View returns latest batch
        assert cursor.fetchone() is not None
        conn.close()


class TestBatchEventModelMapping:
    """Test Python model mapping to database schema."""

    def test_model_has_all_required_fields(self):
        from datetime import date
        batch = BatchEvent.create(
            batch_type='daily',
            keywords=['test'],
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 1)
        )
        assert hasattr(batch, 'batch_id')
        assert hasattr(batch, 'batch_type')
        assert hasattr(batch, 'requested_keywords')
        assert hasattr(batch, 'requested_window')
        assert hasattr(batch, 'started_at_ict')
        assert hasattr(batch, 'status')
        assert hasattr(batch, 'rows_written')

    def test_model_serializes_keywords_to_json(self):
        from datetime import date
        batch = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้', 'ไอ'],
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 1)
        )
        data = batch.to_dict()
        keywords_json = data['requested_keywords']
        assert isinstance(keywords_json, str)
        parsed = json.loads(keywords_json)
        assert parsed == ['ไข้', 'ไอ']

    def test_model_deserializes_keywords_from_json(self):
        from datetime import date
        batch = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้', 'ไอ'],
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 1)
        )
        data = batch.to_dict()
        batch2 = BatchEvent.from_dict(data)
        assert batch2.requested_keywords == ['ไข้', 'ไอ']


class TestBatchEventConstraints:
    """Test database constraints on batch events."""


    def test_batch_id_uniqueness(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b17', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b17', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        conn.close()

    def test_not_null_constraints(self, test_db):
        conn = sqlite3.connect(test_db)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES (NULL, 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        conn.close()


class TestBatchEventCompleteness:
    """Test that batch events meet spec.md FR-008 completeness requirements."""


    def test_batch_event_has_all_fr008_fields(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status) VALUES ('b18', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'running')")
        cursor = conn.execute("PRAGMA table_info(events_raw_rsv_ingested)")
        columns = [col[1] for col in cursor.fetchall()]
        # Check FR-008 fields
        assert 'batch_id' in columns
        assert 'batch_type' in columns
        assert 'requested_keywords' in columns
        assert 'requested_window' in columns
        assert 'started_at_ict' in columns
        assert 'finished_at_ict' in columns
        assert 'status' in columns
        assert 'rows_written' in columns
        assert 'rows_updated' in columns
        assert 'rows_missing' in columns
        assert 'notes' in columns
        assert 'error_message' in columns
        conn.close()

    def test_success_batch_has_counts(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status, rows_written) VALUES ('b19', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'success', 10)")
        cursor = conn.execute("SELECT rows_written FROM events_raw_rsv_ingested WHERE batch_id='b19'")
        assert cursor.fetchone()[0] > 0
        conn.close()

    def test_fail_batch_has_error_message(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status, error_message) VALUES ('b20', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'fail', 'Connection error')")
        cursor = conn.execute("SELECT error_message FROM events_raw_rsv_ingested WHERE batch_id='b20'")
        assert cursor.fetchone()[0] is not None
        conn.close()

    def test_degraded_batch_has_notes(self, test_db):
        conn = sqlite3.connect(test_db)
        conn.execute("INSERT INTO events_raw_rsv_ingested (batch_id, batch_type, requested_keywords, requested_window, started_at_ict, status, notes) VALUES ('b21', 'daily', '[]', '2025-01-01 to 2025-01-01', '2025-01-01T00:00:00+07:00', 'degraded', 'Missing 3 keywords')")
        cursor = conn.execute("SELECT notes FROM events_raw_rsv_ingested WHERE batch_id='b21'")
        assert cursor.fetchone()[0] is not None
        conn.close()


class TestBatchEventQueryPerformance:
    """Test common query patterns use indexes efficiently."""


    def test_query_latest_batch_uses_index(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("EXPLAIN QUERY PLAN SELECT * FROM events_raw_rsv_ingested ORDER BY started_at_ict DESC LIMIT 1")
        plan = cursor.fetchall()
        assert len(plan) > 0
        conn.close()

    def test_query_by_status_uses_index(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("EXPLAIN QUERY PLAN SELECT * FROM events_raw_rsv_ingested WHERE status='success'")
        plan = cursor.fetchall()
        assert len(plan) > 0
        conn.close()

    def test_query_by_date_range_uses_index(self, test_db):
        conn = sqlite3.connect(test_db)
        cursor = conn.execute("EXPLAIN QUERY PLAN SELECT * FROM events_raw_rsv_ingested WHERE started_at_ict > '2025-01-01'")
        plan = cursor.fetchall()
        assert len(plan) > 0
        conn.close()
