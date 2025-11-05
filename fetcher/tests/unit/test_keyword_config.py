"""
Unit Tests for Keyword Configuration Data Model - SPEC-DRIVEN BEHAVIORAL TESTS

Tests ACTUAL KeywordConfig behavior per spec requirements:
- Model creation and validation
- Active/inactive status management
- Province scoping enforcement
- Serialization and deserialization
- Thai keyword support

Constitution alignment:
- Principle III: TDD - Tests written FIRST, validate BEHAVIOR not implementation
- Principle VII: Configuration-as-Code - Keywords managed as data
- Principle IV: Data Governance - Province scoping enforced

Spec references:
- data-model.md: config_keywords table schema
- plan.md: "Keywords managed as configuration data"
"""

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from models.keyword_config import KeywordConfig
from lib.timezone_utils import ICT


class TestKeywordConfigCreation:
    """Test that KeywordConfig ACTUALLY creates valid instances."""

    def test_creates_keyword_with_minimal_fields(self):
        """
        SPEC: Keywords must have term identifier
        BEHAVIOR: KeywordConfig ACTUALLY creates instance with only term
        """
        keyword = KeywordConfig(term='ไข้')

        assert keyword.term == 'ไข้'
        assert keyword.active is True  # Default
        assert keyword.province_code == 'TH-50'  # Default
        assert keyword.notes is None

    def test_creates_keyword_with_all_fields(self):
        """
        SPEC: Keywords support full metadata
        BEHAVIOR: KeywordConfig ACTUALLY stores all specified fields
        """
        now = datetime.now(ICT)

        keyword = KeywordConfig(
            term='ไอ',
            active=False,
            created_at=now,
            province_code='TH-50',
            notes='Test keyword'
        )

        assert keyword.term == 'ไอ'
        assert keyword.active is False
        assert keyword.created_at == now
        assert keyword.province_code == 'TH-50'
        assert keyword.notes == 'Test keyword'

    def test_defaults_active_to_true(self):
        """
        SPEC: New keywords should be active by default
        BEHAVIOR: KeywordConfig ACTUALLY defaults active=True
        """
        keyword = KeywordConfig(term='หวัด')

        assert keyword.active is True

    def test_defaults_province_to_th_50(self):
        """
        SPEC: MVP constraint - TH-50 (Chiang Mai) only
        BEHAVIOR: KeywordConfig ACTUALLY defaults to TH-50
        """
        keyword = KeywordConfig(term='ไอ')

        assert keyword.province_code == 'TH-50'

    def test_sets_created_at_to_ict_timezone(self):
        """
        SPEC: Timestamps must use ICT timezone
        BEHAVIOR: KeywordConfig ACTUALLY uses ICT for created_at
        """
        keyword = KeywordConfig(term='ไข้')

        # Verify timezone ACTUALLY ICT
        assert keyword.created_at.tzinfo == ICT


class TestKeywordConfigValidation:
    """Test that KeywordConfig ACTUALLY validates input fields."""

    def test_raises_error_for_empty_term(self):
        """
        SPEC: Keywords must have non-empty term
        BEHAVIOR: KeywordConfig ACTUALLY rejects empty term
        """
        with pytest.raises(ValueError) as exc_info:
            KeywordConfig(term='')

        assert 'term cannot be empty' in str(exc_info.value).lower()

    def test_raises_error_for_whitespace_only_term(self):
        """
        SPEC: Keywords must have meaningful term
        BEHAVIOR: KeywordConfig ACTUALLY rejects whitespace-only term
        """
        with pytest.raises(ValueError) as exc_info:
            KeywordConfig(term='   ')

        assert 'term cannot be empty' in str(exc_info.value).lower()

    def test_raises_error_for_non_th_50_province(self):
        """
        SPEC: MVP constraint - only TH-50 supported
        BEHAVIOR: KeywordConfig ACTUALLY rejects other provinces
        """
        with pytest.raises(ValueError) as exc_info:
            KeywordConfig(term='ไข้', province_code='TH-10')

        assert 'TH-50' in str(exc_info.value)
        assert 'MVP' in str(exc_info.value)


class TestThaiKeywordSupport:
    """Test that KeywordConfig ACTUALLY handles Thai Unicode correctly."""

    def test_stores_thai_keyword_correctly(self):
        """
        SPEC: System must support Thai language keywords
        BEHAVIOR: KeywordConfig ACTUALLY preserves Thai Unicode
        """
        keyword = KeywordConfig(term='ไข้หวัดนก')

        assert keyword.term == 'ไข้หวัดนก'

    def test_stores_multiple_thai_keywords(self):
        """
        SPEC: System must support multiple Thai keywords
        BEHAVIOR: Multiple KeywordConfig instances ACTUALLY preserve Thai text
        """
        keywords = [
            KeywordConfig(term='ไข้'),
            KeywordConfig(term='ไอ'),
            KeywordConfig(term='หวัด'),
            KeywordConfig(term='อุจจาระร่วง')
        ]

        assert keywords[0].term == 'ไข้'
        assert keywords[1].term == 'ไอ'
        assert keywords[2].term == 'หวัด'
        assert keywords[3].term == 'อุจจาระร่วง'

    def test_notes_field_supports_thai_text(self):
        """
        SPEC: Notes field must support Thai language
        BEHAVIOR: KeywordConfig ACTUALLY preserves Thai Unicode in notes
        """
        keyword = KeywordConfig(
            term='ไข้',
            notes='คำสำคัญสำหรับไข้'
        )

        assert 'คำสำคัญ' in keyword.notes


class TestKeywordActivationDeactivation:
    """Test that KeywordConfig ACTUALLY manages active/inactive status."""

    def test_deactivate_sets_active_to_false(self):
        """
        SPEC: Keywords can be deactivated
        BEHAVIOR: deactivate() ACTUALLY sets active=False
        """
        keyword = KeywordConfig(term='ไข้')
        assert keyword.active is True

        keyword.deactivate('Deprecated term')

        assert keyword.active is False

    def test_deactivate_adds_reason_to_notes(self):
        """
        SPEC: Deactivation must include reason
        BEHAVIOR: deactivate() ACTUALLY appends reason to notes
        """
        keyword = KeywordConfig(term='ไข้')

        keyword.deactivate('No longer relevant')

        assert 'Deactivated' in keyword.notes
        assert 'No longer relevant' in keyword.notes

    def test_deactivate_appends_to_existing_notes(self):
        """
        SPEC: Deactivation should preserve existing notes
        BEHAVIOR: deactivate() ACTUALLY appends to existing notes
        """
        keyword = KeywordConfig(term='ไข้', notes='Original note')

        keyword.deactivate('Superseded by new term')

        assert 'Original note' in keyword.notes
        assert 'Deactivated' in keyword.notes
        assert 'Superseded by new term' in keyword.notes

    def test_activate_sets_active_to_true(self):
        """
        SPEC: Inactive keywords can be reactivated
        BEHAVIOR: activate() ACTUALLY sets active=True
        """
        keyword = KeywordConfig(term='ไข้', active=False)
        assert keyword.active is False

        keyword.activate()

        assert keyword.active is True


class TestKeywordSerialization:
    """Test that KeywordConfig ACTUALLY serializes to dict correctly."""

    def test_to_dict_returns_all_fields(self):
        """
        SPEC: Model must serialize for database storage
        BEHAVIOR: to_dict() ACTUALLY returns complete dictionary
        """
        keyword = KeywordConfig(
            term='ไข้',
            active=True,
            province_code='TH-50',
            notes='Test note'
        )

        data = keyword.to_dict()

        assert isinstance(data, dict)
        assert 'term' in data
        assert 'active' in data
        assert 'created_at' in data
        assert 'province_code' in data
        assert 'notes' in data

    def test_to_dict_converts_datetime_to_string(self):
        """
        SPEC: Serialization must convert datetime for storage
        BEHAVIOR: to_dict() ACTUALLY converts created_at to ISO string
        """
        keyword = KeywordConfig(term='ไข้')

        data = keyword.to_dict()

        # created_at should be string (ISO 8601 format)
        assert isinstance(data['created_at'], str)
        assert 'T' in data['created_at']  # ISO format includes 'T'

    def test_to_dict_preserves_thai_text(self):
        """
        SPEC: Serialization must preserve Thai Unicode
        BEHAVIOR: to_dict() ACTUALLY preserves Thai keywords
        """
        keyword = KeywordConfig(term='ไข้หวัดนก', notes='โน้ตภาษาไทย')

        data = keyword.to_dict()

        assert data['term'] == 'ไข้หวัดนก'
        assert data['notes'] == 'โน้ตภาษาไทย'


class TestKeywordDeserialization:
    """Test that KeywordConfig ACTUALLY deserializes from dict correctly."""

    def test_from_dict_creates_instance_from_dictionary(self):
        """
        SPEC: Model must deserialize from database row
        BEHAVIOR: from_dict() ACTUALLY creates KeywordConfig from dict
        """
        data = {
            'term': 'ไอ',
            'active': True,
            'created_at': '2025-11-04T07:30:00+07:00',
            'province_code': 'TH-50',
            'notes': 'Test keyword'
        }

        keyword = KeywordConfig.from_dict(data)

        assert isinstance(keyword, KeywordConfig)
        assert keyword.term == 'ไอ'
        assert keyword.active is True
        assert keyword.province_code == 'TH-50'
        assert keyword.notes == 'Test keyword'

    def test_from_dict_converts_active_from_int_to_bool(self):
        """
        SPEC: SQLite stores booleans as integers (0/1)
        BEHAVIOR: from_dict() ACTUALLY converts 0/1 to bool
        """
        data_active = {
            'term': 'ไข้',
            'active': 1,  # SQLite representation
            'created_at': '2025-11-04T07:30:00+07:00',
            'province_code': 'TH-50'
        }

        data_inactive = {
            'term': 'หวัด',
            'active': 0,  # SQLite representation
            'created_at': '2025-11-04T07:30:00+07:00',
            'province_code': 'TH-50'
        }

        keyword_active = KeywordConfig.from_dict(data_active)
        keyword_inactive = KeywordConfig.from_dict(data_inactive)

        assert keyword_active.active is True
        assert keyword_inactive.active is False

    def test_from_dict_parses_datetime_from_string(self):
        """
        SPEC: Deserialization must parse ISO datetime strings
        BEHAVIOR: from_dict() ACTUALLY parses created_at from ISO string
        """
        data = {
            'term': 'ไข้',
            'active': True,
            'created_at': '2025-11-04T07:30:00+07:00',
            'province_code': 'TH-50'
        }

        keyword = KeywordConfig.from_dict(data)

        assert isinstance(keyword.created_at, datetime)
        assert keyword.created_at.year == 2025
        assert keyword.created_at.month == 11
        assert keyword.created_at.day == 4

    def test_from_dict_preserves_thai_text(self):
        """
        SPEC: Deserialization must preserve Thai Unicode
        BEHAVIOR: from_dict() ACTUALLY preserves Thai keywords
        """
        data = {
            'term': 'อุจจาระร่วง',
            'active': True,
            'created_at': '2025-11-04T07:30:00+07:00',
            'province_code': 'TH-50',
            'notes': 'คำอธิบายภาษาไทย'
        }

        keyword = KeywordConfig.from_dict(data)

        assert keyword.term == 'อุจจาระร่วง'
        assert keyword.notes == 'คำอธิบายภาษาไทย'


class TestKeywordRoundTripSerialization:
    """Test that serialization and deserialization ACTUALLY preserve data."""

    def test_roundtrip_preserves_all_data(self):
        """
        SPEC: Serialization must be lossless
        BEHAVIOR: to_dict() → from_dict() ACTUALLY preserves all fields
        """
        original = KeywordConfig(
            term='ไข้หวัดนก',
            active=False,
            province_code='TH-50',
            notes='Avian flu keyword'
        )

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = KeywordConfig.from_dict(data)

        # Verify all fields preserved
        assert restored.term == original.term
        assert restored.active == original.active
        assert restored.province_code == original.province_code
        assert restored.notes == original.notes

    def test_roundtrip_with_deactivated_keyword(self):
        """
        SPEC: Deactivated keywords must serialize correctly
        BEHAVIOR: Deactivation state ACTUALLY preserved through roundtrip
        """
        original = KeywordConfig(term='ไอ')
        original.deactivate('No longer used')

        # Serialize
        data = original.to_dict()

        # Deserialize
        restored = KeywordConfig.from_dict(data)

        # Verify deactivation preserved
        assert restored.active is False
        assert 'Deactivated' in restored.notes
        assert 'No longer used' in restored.notes


class TestKeywordRepresentation:
    """Test that KeywordConfig ACTUALLY provides readable string representation."""

    def test_repr_includes_term_and_status(self):
        """
        SPEC: Model should have readable representation
        BEHAVIOR: __repr__() ACTUALLY includes term and active status
        """
        keyword = KeywordConfig(term='ไข้')

        repr_str = repr(keyword)

        assert 'ไข้' in repr_str
        assert 'active' in repr_str

    def test_repr_shows_inactive_for_deactivated_keywords(self):
        """
        SPEC: Representation should show inactive status
        BEHAVIOR: __repr__() ACTUALLY shows 'inactive' for deactivated keywords
        """
        keyword = KeywordConfig(term='หวัด', active=False)

        repr_str = repr(keyword)

        assert 'inactive' in repr_str

    def test_repr_includes_province_code(self):
        """
        SPEC: Representation should show province scoping
        BEHAVIOR: __repr__() ACTUALLY includes province_code
        """
        keyword = KeywordConfig(term='ไอ', province_code='TH-50')

        repr_str = repr(keyword)

        assert 'TH-50' in repr_str
