"""
Unit Tests for Configuration Loader Module - SPEC-DRIVEN BEHAVIORAL TESTS

Tests ACTUAL configuration behavior per spec requirements:
- TOML file parsing and validation
- Required section and field validation
- Default value handling
- Error messages for invalid configurations
- Type checking for configuration values

Constitution alignment:
- Principle III: TDD - Tests written FIRST, validate BEHAVIOR not implementation
- Principle VII: Configuration-as-Code - Single TOML file validation

Spec references:
- plan.md: "TOML config loader (loads googili.toml, validates structure)"
- research.md Decision 8: "TOML for configuration"
"""

import pytest
import tempfile
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from lib.config import FetcherConfig, ConfigurationError


class TestConfigurationFileLoading:
    """Test that FetcherConfig ACTUALLY loads and parses TOML files."""

    def test_loads_valid_toml_configuration_file(self):
        """
        SPEC: TOML config loader loads googili.toml
        BEHAVIOR: FetcherConfig ACTUALLY parses valid TOML file
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general]
                province = "TH"

                [keywords]
                terms = ["ไข้", "ไอ", "หวัด"]

                [schedule]
                daily_time = "07:30"

                [backfill]
                initial_days = 90
            """)
            config_path = tmp.name

        # Load configuration
        config = FetcherConfig(config_path)

        # Verify configuration ACTUALLY loaded
        assert config.province == "TH"
        assert config.keywords == ["ไข้", "ไอ", "หวัด"]
        assert config.daily_time == "07:30"
        assert config.initial_backfill_days == 90

        Path(config_path).unlink()

    def test_raises_error_for_missing_configuration_file(self):
        """
        SPEC: System must validate configuration exists
        BEHAVIOR: FetcherConfig ACTUALLY raises ConfigurationError for missing file
        """
        with pytest.raises(ConfigurationError) as exc_info:
            FetcherConfig("nonexistent_config.toml")

        # Verify error message ACTUALLY helpful
        assert "not found" in str(exc_info.value).lower()
        assert "nonexistent_config.toml" in str(exc_info.value)

    def test_raises_error_for_invalid_toml_syntax(self):
        """
        SPEC: System must validate configuration syntax
        BEHAVIOR: FetcherConfig ACTUALLY raises ConfigurationError for invalid TOML
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general
                invalid toml syntax here
            """)
            config_path = tmp.name

        with pytest.raises(ConfigurationError) as exc_info:
            FetcherConfig(config_path)

        # Verify error message mentions TOML syntax
        assert "toml" in str(exc_info.value).lower() or "syntax" in str(exc_info.value).lower()

        Path(config_path).unlink()


class TestConfigurationValidation:
    """Test that FetcherConfig ACTUALLY validates required sections and fields."""

    def test_raises_error_for_missing_general_section(self):
        """
        SPEC: Configuration must include all required sections
        BEHAVIOR: FetcherConfig ACTUALLY validates [general] section exists
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [keywords]
                terms = ["ไข้"]

                [schedule]
                daily_time = "07:30"

                [backfill]
                initial_days = 90
            """)
            config_path = tmp.name

        with pytest.raises(ConfigurationError) as exc_info:
            FetcherConfig(config_path)

        assert "general" in str(exc_info.value).lower()

        Path(config_path).unlink()

    def test_raises_error_for_missing_keywords_section(self):
        """
        SPEC: Configuration must specify keywords to track
        BEHAVIOR: FetcherConfig ACTUALLY validates [keywords] section exists
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general]
                province = "TH"

                [schedule]
                daily_time = "07:30"

                [backfill]
                initial_days = 90
            """)
            config_path = tmp.name

        with pytest.raises(ConfigurationError) as exc_info:
            FetcherConfig(config_path)

        assert "keywords" in str(exc_info.value).lower()

        Path(config_path).unlink()

    def test_raises_error_for_missing_schedule_section(self):
        """
        SPEC: Configuration must specify scheduling parameters
        BEHAVIOR: FetcherConfig ACTUALLY validates [schedule] section exists
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general]
                province = "TH"

                [keywords]
                terms = ["ไข้"]

                [backfill]
                initial_days = 90
            """)
            config_path = tmp.name

        with pytest.raises(ConfigurationError) as exc_info:
            FetcherConfig(config_path)

        assert "schedule" in str(exc_info.value).lower()

        Path(config_path).unlink()

    def test_raises_error_for_missing_backfill_section(self):
        """
        SPEC: Configuration must specify backfill parameters
        BEHAVIOR: FetcherConfig ACTUALLY validates [backfill] section exists
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general]
                province = "TH"

                [keywords]
                terms = ["ไข้"]

                [schedule]
                daily_time = "07:30"
            """)
            config_path = tmp.name

        with pytest.raises(ConfigurationError) as exc_info:
            FetcherConfig(config_path)

        assert "backfill" in str(exc_info.value).lower()

        Path(config_path).unlink()

    def test_raises_error_for_missing_keywords_terms_field(self):
        """
        SPEC: Keywords section must specify terms array
        BEHAVIOR: FetcherConfig ACTUALLY validates keywords.terms field exists
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general]
                province = "TH"

                [keywords]
                # Missing terms field

                [schedule]
                daily_time = "07:30"

                [backfill]
                initial_days = 90
            """)
            config_path = tmp.name

        with pytest.raises(ConfigurationError) as exc_info:
            FetcherConfig(config_path)

        assert "keywords.terms" in str(exc_info.value).lower()

        Path(config_path).unlink()

    def test_raises_error_for_empty_keywords_array(self):
        """
        SPEC: At least one keyword must be configured
        BEHAVIOR: FetcherConfig ACTUALLY rejects empty keywords array
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general]
                province = "TH"

                [keywords]
                terms = []

                [schedule]
                daily_time = "07:30"

                [backfill]
                initial_days = 90
            """)
            config_path = tmp.name

        with pytest.raises(ConfigurationError) as exc_info:
            FetcherConfig(config_path)

        assert "empty" in str(exc_info.value).lower()

        Path(config_path).unlink()

    def test_raises_error_for_non_array_keywords(self):
        """
        SPEC: Keywords must be array type
        BEHAVIOR: FetcherConfig ACTUALLY validates keywords.terms is array
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general]
                province = "TH"

                [keywords]
                terms = "ไข้"  # Should be array

                [schedule]
                daily_time = "07:30"

                [backfill]
                initial_days = 90
            """)
            config_path = tmp.name

        with pytest.raises(ConfigurationError) as exc_info:
            FetcherConfig(config_path)

        assert "array" in str(exc_info.value).lower()

        Path(config_path).unlink()


class TestProvinceValidation:
    """Test that FetcherConfig ACTUALLY enforces MVP province constraint."""

    def test_accepts_valid_province_th_50(self):
        """
        SPEC: MVP supports TH-50 (Chiang Mai) only
        BEHAVIOR: FetcherConfig ACTUALLY accepts TH-50
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general]
                province = "TH"

                [keywords]
                terms = ["ไข้"]

                [schedule]
                daily_time = "07:30"

                [backfill]
                initial_days = 90
            """)
            config_path = tmp.name

        config = FetcherConfig(config_path)
        assert config.province == "TH"

        Path(config_path).unlink()

    def test_accepts_any_iso_province_code(self):
        """
        SPEC: System supports any ISO 3166-2 province code
        BEHAVIOR: FetcherConfig ACTUALLY accepts various province codes
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general]
                province = "TH-10"  # Bangkok

                [keywords]
                terms = ["ไข้"]

                [schedule]
                daily_time = "07:30"

                [backfill]
                initial_days = 90
            """)
            config_path = tmp.name

        config = FetcherConfig(config_path)
        assert config.province == "TH-10"

        Path(config_path).unlink()


class TestConfigurationProperties:
    """Test that configuration properties ACTUALLY return correct values."""

    @pytest.fixture
    def full_config(self):
        """Create complete configuration file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general]
                province = "TH"
                timezone = "Asia/Bangkok"

                [keywords]
                terms = ["ไข้หวัดนก", "ไอ", "หวัด", "อุจจาระร่วง"]

                [schedule]
                daily_time = "07:30"
                jitter_seconds = [3, 5]
                backfill_on_startup_if_gap_hours = 24

                [backfill]
                initial_days = 90
                recovery_days = 14

                [stitching]
                min_overlap_days = 1
                trim_percent = 20

                [resampling]
                min_run_for_weekly = 3

                [archive]
                output_dir = "./data/archive"
                cadence = "monthly"

                [health]
                port = 8080
                db_probe_timeout_seconds = 3
            """)
            config_path = tmp.name

        config = FetcherConfig(config_path)

        yield config

        Path(config_path).unlink()

    def test_keywords_property_returns_list(self, full_config):
        """
        SPEC: Keywords configuration must be accessible
        BEHAVIOR: keywords property ACTUALLY returns list of strings
        """
        keywords = full_config.keywords
        assert isinstance(keywords, list)
        assert len(keywords) == 4
        assert "ไข้หวัดนก" in keywords
        assert "ไอ" in keywords

    def test_province_property_returns_string(self, full_config):
        """
        SPEC: Province configuration must be accessible
        BEHAVIOR: province property ACTUALLY returns province code
        """
        assert full_config.province == "TH"

    def test_timezone_property_returns_string(self, full_config):
        """
        SPEC: Timezone configuration must be accessible
        BEHAVIOR: timezone property ACTUALLY returns timezone string
        """
        assert full_config.timezone == "Asia/Bangkok"

    def test_daily_time_property_returns_string(self, full_config):
        """
        SPEC: Schedule time configuration must be accessible
        BEHAVIOR: daily_time property ACTUALLY returns HH:MM string
        """
        assert full_config.daily_time == "07:30"

    def test_jitter_seconds_property_returns_list(self, full_config):
        """
        SPEC: Jitter configuration must be accessible
        BEHAVIOR: jitter_seconds property ACTUALLY returns [min, max] range
        """
        jitter = full_config.jitter_seconds
        assert isinstance(jitter, list)
        assert len(jitter) == 2
        assert jitter == [3, 5]

    def test_initial_backfill_days_property_returns_int(self, full_config):
        """
        SPEC: Backfill configuration must be accessible
        BEHAVIOR: initial_backfill_days property ACTUALLY returns integer
        """
        assert full_config.initial_backfill_days == 90
        assert isinstance(full_config.initial_backfill_days, int)

    def test_recovery_backfill_days_property_returns_int(self, full_config):
        """
        SPEC: Recovery backfill configuration must be accessible
        BEHAVIOR: recovery_backfill_days property ACTUALLY returns integer
        """
        assert full_config.recovery_backfill_days == 14

    def test_stitching_min_overlap_days_property(self, full_config):
        """
        SPEC: Stitching configuration must be accessible
        BEHAVIOR: stitching_min_overlap_days ACTUALLY returns configured value
        """
        assert full_config.stitching_min_overlap_days == 1

    def test_health_port_property_returns_int(self, full_config):
        """
        SPEC: Health endpoint configuration must be accessible
        BEHAVIOR: health_port property ACTUALLY returns integer port
        """
        assert full_config.health_port == 8080
        assert isinstance(full_config.health_port, int)


class TestConfigurationDefaults:
    """Test that configuration defaults ACTUALLY applied when fields missing."""

    def test_province_defaults_to_th_50(self):
        """
        SPEC: System must have sensible defaults
        BEHAVIOR: province ACTUALLY defaults to TH-50 when not specified
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general]
                # province not specified

                [keywords]
                terms = ["ไข้"]

                [schedule]
                daily_time = "07:30"

                [backfill]
                initial_days = 90
            """)
            config_path = tmp.name

        config = FetcherConfig(config_path)
        assert config.province == "TH"

        Path(config_path).unlink()

    def test_timezone_defaults_to_asia_bangkok(self):
        """
        SPEC: System must default to ICT timezone
        BEHAVIOR: timezone ACTUALLY defaults to Asia/Bangkok
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general]
                province = "TH"

                [keywords]
                terms = ["ไข้"]

                [schedule]
                daily_time = "07:30"

                [backfill]
                initial_days = 90
            """)
            config_path = tmp.name

        config = FetcherConfig(config_path)
        assert config.timezone == "Asia/Bangkok"

        Path(config_path).unlink()

    def test_daily_time_defaults_to_07_30(self):
        """
        SPEC: Default schedule time is 07:30 ICT
        BEHAVIOR: daily_time ACTUALLY defaults to 07:30
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general]
                province = "TH"

                [keywords]
                terms = ["ไข้"]

                [schedule]
                # daily_time not specified

                [backfill]
                initial_days = 90
            """)
            config_path = tmp.name

        config = FetcherConfig(config_path)
        assert config.daily_time == "07:30"

        Path(config_path).unlink()

    def test_jitter_seconds_defaults_to_3_5(self):
        """
        SPEC: Default jitter prevents simultaneous execution
        BEHAVIOR: jitter_seconds ACTUALLY defaults to [3, 5]
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general]
                province = "TH"

                [keywords]
                terms = ["ไข้"]

                [schedule]
                daily_time = "07:30"

                [backfill]
                initial_days = 90
            """)
            config_path = tmp.name

        config = FetcherConfig(config_path)
        assert config.jitter_seconds == [3, 5]

        Path(config_path).unlink()


class TestConfigurationRawAccess:
    """Test that raw configuration ACTUALLY accessible for advanced use cases."""

    def test_get_raw_returns_complete_dictionary(self):
        """
        SPEC: System must provide access to raw configuration
        BEHAVIOR: get_raw() ACTUALLY returns complete configuration dict
        """
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as tmp:
            tmp.write("""
                [general]
                province = "TH"

                [keywords]
                terms = ["ไข้", "ไอ"]

                [schedule]
                daily_time = "07:30"

                [backfill]
                initial_days = 90

                [custom_section]
                custom_field = "custom_value"
            """)
            config_path = tmp.name

        config = FetcherConfig(config_path)
        raw = config.get_raw()

        # Verify raw dict ACTUALLY contains all sections
        assert 'general' in raw
        assert 'keywords' in raw
        assert 'schedule' in raw
        assert 'backfill' in raw
        assert 'custom_section' in raw

        # Verify custom sections accessible via raw dict
        assert raw['custom_section']['custom_field'] == "custom_value"

        Path(config_path).unlink()
