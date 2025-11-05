"""
Unit Tests for Retry Configuration - HTTP 429 Rate Limiting

Tests that FetcherConfig correctly parses and validates rate_limiting configuration
section from googili.toml.

Constitution alignment:
- Principle III: TDD - Tests written BEFORE implementation (RED phase)
- Principle VII: Configuration-as-Code - Single TOML file

Test Strategy:
- Test default values when rate_limiting section missing
- Test TOML parsing when rate_limiting section present
- Test validation of retry parameters
- Test configuration immutability
"""

import pytest
import tempfile
import tomllib
from pathlib import Path
import sys

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))


class TestRateLimitingConfigDefaults:
    """Test that FetcherConfig provides sensible retry defaults."""

    def test_fetcher_config_has_rate_limiting_defaults_when_section_missing(self):
        """
        SPEC: FR-016 - Retry behavior must work even if not explicitly configured
        BEHAVIOR: Config provides sensible defaults when [rate_limiting] section missing
        """
        from lib.config import FetcherConfig

        # Create minimal config without rate_limiting section
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write("""
[general]
province = "TH-50"
timezone = "Asia/Bangkok"

[keywords]
terms = ["ไข้", "ไอ"]

[schedule]
daily_time = "07:30"
jitter_minutes = [3, 5]
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
            config_path = f.name

        try:
            config = FetcherConfig(config_path)

            # Verify default values
            assert hasattr(config, 'max_retries')
            assert config.max_retries == 3

            assert hasattr(config, 'backoff_base_seconds')
            assert config.backoff_base_seconds == 60

            assert hasattr(config, 'backoff_multiplier')
            assert config.backoff_multiplier == 5.0

            assert hasattr(config, 'max_backoff_seconds')
            assert config.max_backoff_seconds == 1800  # 30 minutes

            assert hasattr(config, 'respect_retry_after')
            assert config.respect_retry_after is True

        finally:
            Path(config_path).unlink()


class TestRateLimitingConfigTOMLParsing:
    """Test that FetcherConfig parses rate_limiting section from TOML."""

    def test_fetcher_config_loads_rate_limiting_from_toml(self):
        """
        SPEC: FR-016 - Retry behavior should be tunable via configuration
        BEHAVIOR: Config parses [rate_limiting] section and overrides defaults
        """
        from lib.config import FetcherConfig

        # Create config with custom rate_limiting values
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write("""
[general]
province = "TH-50"
timezone = "Asia/Bangkok"

[keywords]
terms = ["ไข้", "ไอ", "เจ็บคอ"]

[schedule]
daily_time = "07:30"
jitter_minutes = [3, 5]
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

[rate_limiting]
max_retries = 5
backoff_base_seconds = 30
backoff_multiplier = 2.0
max_backoff_seconds = 900
respect_retry_after = false
""")
            config_path = f.name

        try:
            config = FetcherConfig(config_path)

            # Verify custom values loaded
            assert config.max_retries == 5
            assert config.backoff_base_seconds == 30
            assert config.backoff_multiplier == 2.0
            assert config.max_backoff_seconds == 900
            assert config.respect_retry_after is False

        finally:
            Path(config_path).unlink()

    def test_fetcher_config_allows_partial_rate_limiting_override(self):
        """
        SPEC: FR-016 - Operators should only override what they need
        BEHAVIOR: Missing rate_limiting fields use defaults, present fields override
        """
        from lib.config import FetcherConfig

        # Create config with only some rate_limiting fields
        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write("""
[general]
province = "TH-50"
timezone = "Asia/Bangkok"

[keywords]
terms = ["ไข้"]

[schedule]
daily_time = "07:30"
jitter_minutes = [3, 5]
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

[rate_limiting]
max_retries = 2
""")
            config_path = f.name

        try:
            config = FetcherConfig(config_path)

            # Verify custom value
            assert config.max_retries == 2

            # Verify defaults used for others
            assert config.backoff_base_seconds == 60
            assert config.backoff_multiplier == 5.0
            assert config.max_backoff_seconds == 1800
            assert config.respect_retry_after is True

        finally:
            Path(config_path).unlink()


class TestRateLimitingConfigValidation:
    """Test that FetcherConfig validates rate_limiting parameters."""

    def test_fetcher_config_rejects_negative_max_retries(self):
        """
        SPEC: FR-016 - Configuration validation must prevent invalid retry settings
        BEHAVIOR: max_retries < 0 raises ConfigException
        """
        from lib.config import FetcherConfig
        from lib.exceptions import ConfigException

        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write("""
[general]
province = "TH-50"
timezone = "Asia/Bangkok"

[keywords]
terms = ["ไข้"]

[schedule]
daily_time = "07:30"
jitter_minutes = [3, 5]
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

[rate_limiting]
max_retries = -1
""")
            config_path = f.name

        try:
            with pytest.raises(ConfigException, match="max_retries must be >= 0"):
                FetcherConfig(config_path)
        finally:
            Path(config_path).unlink()

    def test_fetcher_config_rejects_negative_backoff_base(self):
        """
        SPEC: FR-016 - Backoff times must be positive
        BEHAVIOR: backoff_base_seconds <= 0 raises ConfigException
        """
        from lib.config import FetcherConfig
        from lib.exceptions import ConfigException

        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write("""
[general]
province = "TH-50"
timezone = "Asia/Bangkok"

[keywords]
terms = ["ไข้"]

[schedule]
daily_time = "07:30"
jitter_minutes = [3, 5]
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

[rate_limiting]
backoff_base_seconds = 0
""")
            config_path = f.name

        try:
            with pytest.raises(ConfigException, match="backoff_base_seconds must be > 0"):
                FetcherConfig(config_path)
        finally:
            Path(config_path).unlink()

    def test_fetcher_config_rejects_invalid_backoff_multiplier(self):
        """
        SPEC: FR-016 - Exponential backoff requires multiplier > 1
        BEHAVIOR: backoff_multiplier <= 1.0 raises ConfigException
        """
        from lib.config import FetcherConfig
        from lib.exceptions import ConfigException

        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write("""
[general]
province = "TH-50"
timezone = "Asia/Bangkok"

[keywords]
terms = ["ไข้"]

[schedule]
daily_time = "07:30"
jitter_minutes = [3, 5]
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

[rate_limiting]
backoff_multiplier = 0.5
""")
            config_path = f.name

        try:
            with pytest.raises(ConfigException, match="backoff_multiplier must be > 1.0"):
                FetcherConfig(config_path)
        finally:
            Path(config_path).unlink()


class TestRateLimitingConfigAccessors:
    """Test that rate_limiting config values are accessible as properties."""

    def test_rate_limiting_config_accessible_via_properties(self):
        """
        SPEC: FR-016 - TrendsFetcher needs to access retry configuration
        BEHAVIOR: Config exposes rate_limiting values as read-only properties
        """
        from lib.config import FetcherConfig

        with tempfile.NamedTemporaryFile(mode='w', suffix='.toml', delete=False) as f:
            f.write("""
[general]
province = "TH-50"
timezone = "Asia/Bangkok"

[keywords]
terms = ["ไข้", "ไอ"]

[schedule]
daily_time = "07:30"
jitter_minutes = [3, 5]
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

[rate_limiting]
max_retries = 4
backoff_base_seconds = 45
backoff_multiplier = 3.0
max_backoff_seconds = 600
respect_retry_after = true
""")
            config_path = f.name

        try:
            config = FetcherConfig(config_path)

            # Verify all properties accessible
            assert isinstance(config.max_retries, int)
            assert isinstance(config.backoff_base_seconds, int)
            assert isinstance(config.backoff_multiplier, float)
            assert isinstance(config.max_backoff_seconds, int)
            assert isinstance(config.respect_retry_after, bool)

            # Verify correct values
            assert config.max_retries == 4
            assert config.backoff_base_seconds == 45
            assert config.backoff_multiplier == 3.0
            assert config.max_backoff_seconds == 600
            assert config.respect_retry_after is True

        finally:
            Path(config_path).unlink()
