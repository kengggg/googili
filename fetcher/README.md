# GOOGILI Fetcher Core

Google Trends RSV Data Ingestion for ILI Surveillance

## Overview

The Fetcher core reliably ingests Google Trends Relative Search Volume (RSV) data for ~10 Thai ILI-related keywords in Chiang Mai Province. It produces a stitched, provenance-rich daily time series with complete audit trails.

## Quick Start

### Prerequisites

- Python 3.11+
- Docker 20.10+ and Docker Compose 2.0+ (for containerized deployment)
- Internet access to Google Trends

### Local Development

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure keywords
cp config/googili.toml.example config/googili.toml
# Edit config/googili.toml with your keywords

# Initialize database
python -m fetcher.cli.main --init-db

# Run daily ingestion (manual)
python -m fetcher.cli.main --daily

# Run in daemon mode (scheduled)
python -m fetcher.cli.main --daemon
```

### Docker Deployment

```bash
# Build and start
docker compose up -d fetcher

# Check health
curl http://localhost:8080/healthz

# View logs
docker compose logs -f fetcher

# Manual backfill
docker exec googili_fetcher python -m fetcher.cli.main --backfill --days=90
```

## Configuration

Edit `config/googili.toml`:

- **keywords**: List of Thai search terms to track
- **province**: Geographic scope (default: TH-50 for Chiang Mai)
- **schedule**: Daily ingestion time and jitter settings
- **backfill**: Initial and recovery backfill parameters
- **stitching**: Overlap-based stitching configuration
- **archive**: Monthly snapshot settings

See [quickstart.md](../specs/001-fetcher-core/quickstart.md) for detailed operator runbook.

## Architecture

- **Models**: Domain entities (RSV Record, Batch Event, Keyword Config)
- **Services**: Business logic (TrendsFetcher, Stitcher, Resampler, Ingestion, Archiver)
- **CLI**: Command-line interface and APScheduler daemon
- **Lib**: Infrastructure (database, config, logging, health endpoint)

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=fetcher --cov-report=html

# Run specific test suites
pytest tests/unit/
pytest tests/integration/
pytest tests/contract/
pytest tests/golden/
```

## Health Monitoring

The `/healthz` endpoint returns:

```json
{
  "status": "success",
  "last_fetch": "2025-11-04T07:32:15+07:00",
  "last_batch_id": "batch_20251104_073215",
  "rows_written": 10,
  "true_daily": 10,
  "weekly_flat": 0,
  "missing": 0,
  "db_writable": true
}
```

- `200 OK` + `status: success` = Normal operation
- `200 OK` + `status: degraded` = Last fetch >24h ago
- `503 Service Unavailable` = Critical failure

## Documentation

- [Technical Plan](../specs/001-fetcher-core/plan.md)
- [Feature Specification](../specs/001-fetcher-core/spec.md)
- [Data Model](../specs/001-fetcher-core/data-model.md)
- [Operator Quickstart](../specs/001-fetcher-core/quickstart.md)
- [Research Decisions](../specs/001-fetcher-core/research.md)

## License

See project root LICENSE file.

## Constitution Alignment

This implementation follows the GOOGILI Constitution v1.1.0:

- **Principle I**: Adjunct Signal, Not Diagnostic - No interpretation, only data ingestion
- **Principle II**: Separation of Concerns - Fetcher writes; Analyser/Visualiser read
- **Principle III**: TDD - All core logic has tests written first
- **Principle IV**: Data Governance - Complete provenance metadata in all batch events
- **Principle V**: Fail-Safe - Health endpoint enables independent operation
- **Principle VI**: Clarity Over Cleverness - Simple trimmed mean stitching
- **Principle VII**: Config-as-Code - Single TOML file, version-controlled
- **Principle VIII**: Observability - Structured JSON logs, batch event metadata
- **Principle IX**: Ethical Communication - Honest quality flags, explicit caveats
