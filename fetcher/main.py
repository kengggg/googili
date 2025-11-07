#!/usr/bin/env python3
"""
Fetcher CLI Entry Point

Simplified command-line interface for RSV data ingestion.

Usage:
    # Run ingestion (fetches past ~30 days using 'today 1-m')
    python main.py

    # Custom database path
    python main.py --db /path/to/custom.db

    # Debug logging
    python main.py --log-level DEBUG

Per simplified requirements:
- Fetches past 30 days of daily RSV data using pytrends 'today 1-m' format
- Idempotent - safe to re-run
- Upserts data into database

Constitution alignment:
- Principle VI: Clarity Over Cleverness - Simple, single-purpose CLI
- Principle VIII: Observability - Structured logging throughout
"""

import sys
import argparse
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from lib.db import init_database
from lib.logging_utils import setup_logging
from lib.config import FetcherConfig
from services.ingestion import IngestionService
from lib.timezone_utils import now_ict

logger = logging.getLogger(__name__)


def parse_args():
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="RSV Data Fetcher - Google Trends ingestion for Thailand",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run ingestion (default)
  python main.py

  # Custom database path
  python main.py --db /path/to/custom.db

  # Debug logging
  python main.py --log-level DEBUG
        """
    )

    # Optional arguments
    parser.add_argument(
        '--db',
        type=str,
        default='../data/raw/rsv_trends.db',
        help='Database file path (default: ../data/raw/rsv_trends.db)'
    )
    parser.add_argument(
        '--schema',
        type=str,
        default='schema.sql',
        help='Schema file path (default: schema.sql)'
    )
    parser.add_argument(
        '--log-level',
        type=str,
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level (default: INFO)'
    )

    return parser.parse_args()


def run_ingestion(db_path: str, schema_path: str):
    """
    Run RSV ingestion (fetch past ~30 days using 'today 1-m').

    Args:
        db_path: Database file path
        schema_path: Schema file path

    Returns:
        Exit code (0 for success/degraded, 1 for failure)
    """
    logger.info("=== RSV INGESTION (past 30 days) ===")

    db = None
    try:
        # Initialize database
        db = init_database(schema_path, db_path)

        # Load configuration
        config = FetcherConfig()

        # Run ingestion
        ingestion_service = IngestionService(db, config)
        batch_event = ingestion_service.ingest()

        # Log results
        logger.info(
            f"Ingestion complete: batch_id={batch_event.batch_id}, "
            f"status={batch_event.status}, rows_written={batch_event.rows_written}, "
            f"rows_updated={batch_event.rows_updated}, duration={batch_event.duration_seconds():.1f}s"
        )

        if batch_event.status == 'success':
            logger.info("Ingestion successful")
            return 0
        elif batch_event.status == 'degraded':
            logger.warning(f"Ingestion degraded: {batch_event.notes}")
            return 0  # Still exit 0 for partial success
        else:
            logger.error(f"Ingestion failed: {batch_event.error_message}")
            return 1
    finally:
        if db:
            db.close()
            logger.debug("Database connection closed")


def main():
    """
    Main entry point.
    """
    # Parse arguments
    args = parse_args()

    # Setup logging
    log_level = getattr(logging, args.log_level)
    setup_logging(level=log_level)

    logger.info(f"RSV Fetcher started: {now_ict().strftime('%Y-%m-%d %H:%M:%S %Z')}")

    # Run ingestion
    try:
        sys.exit(run_ingestion(args.db, args.schema))
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
