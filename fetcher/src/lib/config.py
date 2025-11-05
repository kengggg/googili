"""
Configuration Loader Module

Loads and validates TOML configuration per research.md Decision 8.

Constitution alignment:
- Principle VII: Configuration-as-Code - Single TOML file, version-controlled
"""

import sys
import logging
from pathlib import Path
from typing import List, Dict, Any
from lib.exceptions import ConfigException

# Python 3.11+ has tomllib in stdlib, <3.11 needs tomli
if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

# Fix 8: Add logger for configuration events
logger = logging.getLogger(__name__)


# Alias for backward compatibility
ConfigurationError = ConfigException


class FetcherConfig:
    """
    Fetcher configuration loaded from googili.toml.

    Validates structure and provides typed access to all configuration parameters.
    """

    def __init__(self, config_path: str = "config/googili.toml"):
        """
        Load configuration from TOML file.

        Args:
            config_path: Path to googili.toml file

        Raises:
            ConfigurationError: If config file missing or invalid
        """
        self.config_path = Path(config_path)

        # Fix 8: Log configuration loading
        logger.info(f"Loading configuration from {config_path}")

        if not self.config_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            raise ConfigurationError(
                f"Configuration file not found: {config_path}. "
                f"Copy config/googili.toml.example to config/googili.toml and customize."
            )

        # Load TOML
        try:
            with open(self.config_path, 'rb') as f:
                self._config = tomllib.load(f)
            logger.debug(f"Successfully parsed TOML from {config_path}")
        except Exception as e:
            logger.error(f"Failed to parse TOML configuration: {e}")
            raise ConfigurationError(f"Invalid TOML syntax in {config_path}: {e}")

        # Validate required sections
        self._validate()
        logger.info(f"Configuration validated successfully (province={self.province}, keywords={len(self.keywords)})")

    def _validate(self) -> None:
        """Validate configuration structure and required fields."""
        required_sections = ['general', 'keywords', 'schedule', 'backfill']
        for section in required_sections:
            if section not in self._config:
                raise ConfigurationError(f"Missing required section: [{section}]")

        # Validate keywords
        if 'terms' not in self._config['keywords']:
            raise ConfigurationError("Missing required field: keywords.terms")
        if not isinstance(self._config['keywords']['terms'], list):
            raise ConfigurationError("keywords.terms must be an array")
        if len(self._config['keywords']['terms']) == 0:
            raise ConfigurationError("keywords.terms cannot be empty")

        # Validate province
        province = self._config['general'].get('province', 'TH-50')
        if province != 'TH-50':
            raise ConfigurationError(
                f"MVP constraint: Only TH-50 (Chiang Mai) supported. Got: {province}"
            )

        # Validate rate_limiting configuration (optional section, but validate if present)
        if 'rate_limiting' in self._config:
            rl = self._config['rate_limiting']

            # Validate max_retries
            if 'max_retries' in rl:
                if not isinstance(rl['max_retries'], int) or rl['max_retries'] < 0:
                    raise ConfigurationError("max_retries must be >= 0")

            # Validate backoff_base_seconds
            if 'backoff_base_seconds' in rl:
                if not isinstance(rl['backoff_base_seconds'], int) or rl['backoff_base_seconds'] <= 0:
                    raise ConfigurationError("backoff_base_seconds must be > 0")

            # Validate backoff_multiplier
            if 'backoff_multiplier' in rl:
                if not isinstance(rl['backoff_multiplier'], (int, float)) or rl['backoff_multiplier'] <= 1.0:
                    raise ConfigurationError("backoff_multiplier must be > 1.0")

    @property
    def keywords(self) -> List[str]:
        """Get list of Thai keywords to track."""
        return self._config['keywords']['terms']

    @property
    def province(self) -> str:
        """Get province code (ISO 3166-2)."""
        return self._config['general'].get('province', 'TH-50')

    @property
    def timezone(self) -> str:
        """Get timezone for timestamps (default: Asia/Bangkok)."""
        return self._config['general'].get('timezone', 'Asia/Bangkok')

    @property
    def daily_time(self) -> str:
        """Get scheduled daily ingestion time (HH:MM format)."""
        return self._config['schedule'].get('daily_time', '07:30')

    @property
    def jitter_minutes(self) -> List[int]:
        """Get jitter range in minutes [min, max]."""
        return self._config['schedule'].get('jitter_minutes', [3, 5])

    @property
    def backfill_on_startup_gap_hours(self) -> int:
        """Hours gap threshold to trigger recovery backfill on startup."""
        return self._config['schedule'].get('backfill_on_startup_if_gap_hours', 24)

    @property
    def initial_backfill_days(self) -> int:
        """Days to backfill on first run (empty database)."""
        return self._config['backfill'].get('initial_days', 90)

    @property
    def recovery_backfill_days(self) -> int:
        """Days to backfill after outage >24h."""
        return self._config['backfill'].get('recovery_days', 14)

    @property
    def stitching_min_overlap_days(self) -> int:
        """Minimum overlap days for stitching (warn if less)."""
        return self._config.get('stitching', {}).get('min_overlap_days', 1)

    @property
    def stitching_trim_percent(self) -> int:
        """Trim percentage for trimmed mean (0-50)."""
        return self._config.get('stitching', {}).get('trim_percent', 20)

    @property
    def resampling_min_run_for_weekly(self) -> int:
        """Minimum consecutive missing days to trigger weekly promotion."""
        return self._config.get('resampling', {}).get('min_run_for_weekly', 3)

    @property
    def archive_output_dir(self) -> str:
        """Directory for monthly archives."""
        return self._config.get('archive', {}).get('output_dir', './data/archive')

    @property
    def archive_cadence(self) -> str:
        """Archive cadence (monthly)."""
        return self._config.get('archive', {}).get('cadence', 'monthly')

    @property
    def health_port(self) -> int:
        """Health endpoint port."""
        return self._config.get('health', {}).get('port', 8080)

    @property
    def health_db_probe_timeout_seconds(self) -> int:
        """Database probe timeout for health check."""
        return self._config.get('health', {}).get('db_probe_timeout_seconds', 3)

    @property
    def max_retries(self) -> int:
        """Maximum retry attempts for HTTP 429 errors."""
        return self._config.get('rate_limiting', {}).get('max_retries', 3)

    @property
    def backoff_base_seconds(self) -> int:
        """Base backoff time in seconds for exponential backoff."""
        return self._config.get('rate_limiting', {}).get('backoff_base_seconds', 60)

    @property
    def backoff_multiplier(self) -> float:
        """Exponential backoff multiplier."""
        return self._config.get('rate_limiting', {}).get('backoff_multiplier', 5.0)

    @property
    def max_backoff_seconds(self) -> int:
        """Maximum backoff time cap in seconds."""
        return self._config.get('rate_limiting', {}).get('max_backoff_seconds', 1800)

    @property
    def respect_retry_after(self) -> bool:
        """Whether to respect Retry-After header from API."""
        return self._config.get('rate_limiting', {}).get('respect_retry_after', True)

    def get_raw(self) -> Dict[str, Any]:
        """Get raw configuration dictionary."""
        return self._config
