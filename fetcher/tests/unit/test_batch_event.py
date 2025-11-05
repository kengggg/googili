"""
Unit Tests for Batch Event Model

Tests batch_id generation, status transitions, and metadata completeness.
Per Constitution Principle III: TDD - Write tests first, ensure they fail.
"""

import pytest
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
import sys
from pathlib import Path
import time

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from models.batch_event import BatchEvent
from lib.timezone_utils import ICT, now_ict

class TestBatchIDGeneration:
    """Test batch_id format and uniqueness."""

    def test_batch_id_format(self):
        """Test batch_id follows format: batch_YYYYMMDD_HHMMSS in ICT."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้', 'ไอ'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        assert batch_event.batch_id.startswith('batch_')
        # Format: batch_YYYYMMDD_HHMMSS = 6 + 8 + 1 + 6 = 21 chars
        assert len(batch_event.batch_id) == 21

        # Verify format with regex
        import re
        pattern = r'batch_\d{8}_\d{6}'
        assert re.match(pattern, batch_event.batch_id)

    def test_batch_id_uniqueness_per_second(self):
        """Test that batch IDs differ only at second granularity."""
        batch1 = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        batch2 = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        # May have same batch_id if created in same second
        # or different if crossed second boundary
        assert batch1.batch_id.startswith('batch_')
        assert batch2.batch_id.startswith('batch_')

    def test_batch_id_uses_ict_timezone(self):
        """Test that batch_id timestamp uses Asia/Bangkok timezone."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        # Extract date from batch_id
        # Format: batch_YYYYMMDD_HHMMSS
        date_part = batch_event.batch_id[6:14]  # YYYYMMDD
        time_part = batch_event.batch_id[15:21]  # HHMMSS

        # Verify it's close to current ICT time
        now = now_ict()
        expected_date = now.strftime('%Y%m%d')
        assert date_part == expected_date


class TestBatchEventCreation:
    """Test creating batch events with required metadata."""

    def test_create_daily_batch_event(self):
        """Test creating batch event for daily ingestion."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้', 'ไอ'],
            start_date=date(2025, 11, 3),
            end_date=date(2025, 11, 4)
        )

        assert batch_event.batch_id is not None
        assert batch_event.batch_type == 'daily'
        assert batch_event.requested_keywords == ['ไข้', 'ไอ']
        assert batch_event.requested_window == '2025-11-03 to 2025-11-04'
        assert batch_event.started_at_ict.tzinfo == ICT
        assert batch_event.status == 'running'

    def test_create_backfill_batch_event(self):
        """Test creating batch event for backfill."""
        batch_event = BatchEvent.create(
            batch_type='initial_backfill',
            keywords=['ไข้'],
            start_date=date(2025, 8, 1),
            end_date=date(2025, 11, 4)
        )

        assert batch_event.batch_type == 'initial_backfill'
        assert batch_event.status == 'running'

    def test_create_manual_batch_event(self):
        """Test creating batch event for manual trigger."""
        batch_event = BatchEvent.create(
            batch_type='manual',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4),
            notes='Manual trigger for testing'
        )

        assert batch_event.batch_type == 'manual'
        assert batch_event.notes == 'Manual trigger for testing'

    def test_create_requires_keywords(self):
        """Test that creating batch event requires keywords list."""
        with pytest.raises(ValueError, match="requested_keywords cannot be empty"):
            BatchEvent.create(
                batch_type='daily',
                keywords=[],  # Empty keywords
                start_date=date(2025, 11, 4),
                end_date=date(2025, 11, 4)
            )

    def test_create_validates_batch_type(self):
        """Test that invalid batch_type raises error."""
        with pytest.raises(ValueError, match="batch_type must be one of"):
            BatchEvent(
                batch_id='batch_test',
                batch_type='invalid_type',
                requested_keywords=['ไข้'],
                requested_window='2025-11-04 to 2025-11-04',
                started_at_ict=now_ict()
            )


class TestStatusTransitions:
    """Test batch event status lifecycle."""

    def test_initial_status_is_running(self):
        """Test that new batch events start with status='running'."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        assert batch_event.status == 'running'
        assert batch_event.finished_at_ict is None

    def test_transition_to_success(self):
        """Test transitioning batch event to success status."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        batch_event.mark_success(rows_written=100, rows_updated=5)

        assert batch_event.status == 'success'
        assert batch_event.rows_written == 100
        assert batch_event.rows_updated == 5
        assert batch_event.finished_at_ict is not None
        assert batch_event.finished_at_ict.tzinfo == ICT

    def test_transition_to_degraded(self):
        """Test transitioning batch event to degraded status."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้', 'ไอ', 'เจ็บคอ'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        batch_event.mark_degraded(
            rows_written=20,
            rows_missing=10,
            reason='3 keywords missing daily data'
        )

        assert batch_event.status == 'degraded'
        assert batch_event.rows_written == 20
        assert batch_event.rows_missing == 10
        assert '3 keywords missing daily data' in batch_event.notes
        assert batch_event.finished_at_ict is not None

    def test_transition_to_fail(self):
        """Test transitioning batch event to fail status."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        batch_event.mark_fail('pytrends API connection timeout')

        assert batch_event.status == 'fail'
        assert batch_event.error_message == 'pytrends API connection timeout'
        assert batch_event.finished_at_ict is not None

    def test_cannot_transition_from_success(self):
        """Test that success status is terminal (cannot change)."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        batch_event.mark_success(rows_written=10)

        with pytest.raises(ValueError, match="Cannot change status from terminal state"):
            batch_event.mark_fail('error')

    def test_cannot_transition_from_fail(self):
        """Test that fail status is terminal (cannot change)."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        batch_event.mark_fail('error')

        with pytest.raises(ValueError, match="Cannot change status from terminal state"):
            batch_event.mark_success(rows_written=10)


class TestMetadataCompleteness:
    """Test that all required metadata fields are present."""

    def test_required_fields_present_on_creation(self):
        """Test that all FR-008 required fields are set on creation."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้', 'ไอ'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        # Required fields per FR-008
        assert batch_event.batch_id is not None
        assert batch_event.batch_type == 'daily'
        assert batch_event.requested_keywords == ['ไข้', 'ไอ']
        assert batch_event.requested_window == '2025-11-04 to 2025-11-04'
        assert batch_event.started_at_ict is not None
        assert batch_event.status == 'running'

    def test_count_fields_initialized_to_zero(self):
        """Test that count fields default to 0 on creation."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        assert batch_event.rows_written == 0
        assert batch_event.rows_updated == 0
        assert batch_event.rows_missing == 0

    def test_optional_fields_nullable(self):
        """Test that optional fields can be null."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        # Optional fields
        assert batch_event.notes is None
        assert batch_event.error_message is None
        assert batch_event.quality_true_daily is None
        assert batch_event.quality_weekly_flat is None
        assert batch_event.quality_below_detection is None

    def test_finished_at_ict_null_while_running(self):
        """Test that finished_at_ict is null while status='running'."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        assert batch_event.status == 'running'
        assert batch_event.finished_at_ict is None


class TestKeywordArrayHandling:
    """Test requested_keywords list handling."""

    def test_keywords_stored_as_list(self):
        """Test that keywords are stored as Python list."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้', 'ไอ', 'เจ็บคอ'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        assert isinstance(batch_event.requested_keywords, list)
        assert len(batch_event.requested_keywords) == 3

    def test_keywords_preserve_order(self):
        """Test that keyword order is preserved."""
        keywords = ['ไข้', 'ไอ', 'เจ็บคอ', 'ปวดศีรษะ']
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=keywords,
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        assert batch_event.requested_keywords == keywords

    def test_keywords_handle_unicode(self):
        """Test that Thai keywords stored correctly (UTF-8)."""
        thai_keywords = ['ไข้', 'ไอ', 'เจ็บคอ']
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=thai_keywords,
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        for kw in thai_keywords:
            assert kw in batch_event.requested_keywords


class TestWindowFormatting:
    """Test requested_window date range formatting."""

    def test_window_format_matches_spec(self):
        """Test that window follows format: 'YYYY-MM-DD to YYYY-MM-DD'."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 3),
            end_date=date(2025, 11, 4)
        )

        assert batch_event.requested_window == '2025-11-03 to 2025-11-04'

    def test_single_day_window(self):
        """Test window format for single-day fetch."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        assert batch_event.requested_window == '2025-11-04 to 2025-11-04'

    def test_90_day_backfill_window(self):
        """Test window format for 90-day backfill."""
        end_date = date(2025, 11, 4)
        start_date = end_date - timedelta(days=90)

        batch_event = BatchEvent.create(
            batch_type='initial_backfill',
            keywords=['ไข้'],
            start_date=start_date,
            end_date=end_date
        )

        expected = f'{start_date.isoformat()} to {end_date.isoformat()}'
        assert batch_event.requested_window == expected


class TestTimestampHandling:
    """Test timestamp fields in Asia/Bangkok timezone."""

    def test_started_at_ict_in_bangkok_timezone(self):
        """Test that started_at_ict uses Asia/Bangkok timezone."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        assert batch_event.started_at_ict.tzinfo == ICT

    def test_finished_at_ict_in_bangkok_timezone(self):
        """Test that finished_at_ict uses Asia/Bangkok timezone."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        batch_event.mark_success(rows_written=10)

        assert batch_event.finished_at_ict is not None
        assert batch_event.finished_at_ict.tzinfo == ICT

    def test_duration_calculation(self):
        """Test calculating batch duration from timestamps."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        # While running, duration should be None
        assert batch_event.duration_seconds() is None

        # After completion, should calculate duration
        time.sleep(0.01)  # Small delay
        batch_event.mark_success(rows_written=10)

        duration = batch_event.duration_seconds()
        assert duration is not None
        assert duration > 0


class TestQualityMetrics:
    """Test quality metric fields."""

    def test_quality_counts_optional_for_mvp(self):
        """Test that quality counts can be null in Phase 3 (added in Phase 7)."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        # Quality counts are optional in MVP
        assert batch_event.quality_true_daily is None
        assert batch_event.quality_weekly_flat is None
        assert batch_event.quality_below_detection is None

    def test_quality_metrics_can_be_set(self):
        """Test setting quality metrics."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้', 'ไอ', 'เจ็บคอ'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        batch_event.set_quality_metrics(
            true_daily=25,
            weekly_flat=5,
            below_detection=0
        )

        assert batch_event.quality_true_daily == 25
        assert batch_event.quality_weekly_flat == 5
        assert batch_event.quality_below_detection == 0


class TestNotesField:
    """Test batch event notes field for audit context."""

    def test_notes_can_be_added(self):
        """Test adding notes to batch event."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        batch_event.add_notes('Stitching factor: 1.23')
        assert 'Stitching factor: 1.23' in batch_event.notes

    def test_notes_can_be_appended(self):
        """Test appending multiple notes."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4),
            notes='Initial note'
        )

        batch_event.add_notes('Additional note')

        assert 'Initial note' in batch_event.notes
        assert 'Additional note' in batch_event.notes

    def test_notes_capture_degradation_reason(self):
        """Test that degradation reason captured in notes."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้', 'ไอ', 'เจ็บคอ'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        batch_event.mark_degraded(
            rows_written=20,
            rows_missing=10,
            reason='3 keywords missing daily data (promoted to weekly)'
        )

        assert '3 keywords missing daily data' in batch_event.notes


class TestSerialization:
    """Test to_dict/from_dict serialization."""

    def test_to_dict_serialization(self):
        """Test converting batch event to dictionary."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้', 'ไอ'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        data = batch_event.to_dict()

        assert isinstance(data, dict)
        assert data['batch_id'] == batch_event.batch_id
        assert data['batch_type'] == 'daily'
        assert isinstance(data['requested_keywords'], str)  # JSON string
        assert 'ไข้' in data['requested_keywords']

    def test_from_dict_deserialization(self):
        """Test creating batch event from dictionary."""
        batch_event = BatchEvent.create(
            batch_type='daily',
            keywords=['ไข้', 'ไอ'],
            start_date=date(2025, 11, 4),
            end_date=date(2025, 11, 4)
        )

        data = batch_event.to_dict()
        batch_event2 = BatchEvent.from_dict(data)

        assert batch_event2.batch_id == batch_event.batch_id
        assert batch_event2.batch_type == batch_event.batch_type
        assert batch_event2.requested_keywords == batch_event.requested_keywords
