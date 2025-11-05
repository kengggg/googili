# Implementation Plan: Fetcher Core - Google Trends RSV Data Ingestion

**Branch**: `001-fetcher-core` | **Date**: 2025-11-04 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-fetcher-core/spec.md`

## Summary

Build the minimum Fetcher core that reliably ingests Google Trends RSV for ~10 Thai ILI-related keywords (Chiang Mai), produces a stitched, provenance-rich daily series, and emits ingestion events for downstream cores—fully aligned with the Googili constitution v1.1.0.

**Key Capabilities**: Daily + on-demand ingestion with 90-day historical backfill; overlap-based stitching for continuous time series; sparse-day resampling with quality flags; append-only event emission; health endpoint; monthly archives; config-as-code.

**Strict Boundaries (Constitution Principle II)**: Fetcher writes raw RSV + batch events to SQLite; no analysis, no dashboards, no cross-core function calls. Communication strictly via database tables and `/healthz` endpoint.

## Technical Context

**Language/Version**: Python 3.11 (slim)

**Primary Dependencies**:
- `pytrends` (Google Trends unofficial API client)
- `APScheduler` (in-container scheduling with jitter)
- `sqlite3` (built-in, with WAL mode)
- Flask/FastAPI (tiny HTTP server for `/healthz`)

**Storage**: SQLite 3 with WAL mode; single file for MVP (raw_trenddata, events_raw_rsv_ingested, config_keywords tables)

**Testing**: pytest with:
- Unit tests (stitching, windowing, idempotence)
- Golden-file tests (known overlap scenarios)
- Contract tests (event emission, Analyser can read fields)

**Target Platform**: Linux server (Docker container); Asia/Bangkok timezone

**Project Type**: Single backend service (CLI + scheduled daemon)

**Performance Goals**:
- Daily fetch+stitch per keyword < 60 seconds
- 90-day backfill completes within 15 minutes for 10 keywords
- `/healthz` responds < 100ms

**Constraints**:
- Timeliness: Daily ingestion by 07:30 ICT (constitution requirement)
- Zero duplicates: unique (keyword, date) constraint enforced
- Append-only: historical rows change only during explicit logged backfill

**Scale/Scope**:
- 10 Thai keywords (Chiang Mai TH-50)
- 90+ days of daily records per keyword
- Modest hardware (2 CPU, 4GB RAM)
- Single-server deployment

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Principle I: Adjunct Signal, Not Diagnostic ✅
- Fetcher emits raw RSV with explicit caveats in batch event notes
- No interpretation, no thresholds, no analysis—strictly data ingestion
- Granularity flags (true_daily vs. weekly_flat) preserve honesty about data quality

### Principle II: Separation of Concerns (Three Cores) ✅
- **Strict boundary**: Fetcher writes; Analyser/Visualiser read
- Communication via database events (`events_raw_rsv_ingested`) and `/healthz` only
- No direct function calls; each core runs independently
- **Decision**: Shared SQLite file mounted in Docker for MVP; clean boundary via table contracts

### Principle III: Test-Driven Development (NON-NEGOTIABLE) ✅
- TDD mandatory for all core logic:
  - Unit: stitching algorithm, overlap window calculation, UPSERT idempotence
  - Golden-file: known overlap/gap scenarios validate stitching integrity
  - Contract: Analyser can parse batch events; ingestion appends exactly once
- Red-Green-Refactor cycle enforced in development workflow

### Principle IV: Data Governance & Provenance ✅
- Every batch event records: batch_id, keywords, window, row counts, timestamps (ICT)
- Every RSV record includes: raw value, stitched value, source window, batch_id, granularity/quality flags
- Monthly archives saved to `./archive` with data dictionary
- No personal data; only aggregated RSV values

### Principle V: Fail-Safe & Availability ✅
- `/healthz` endpoint reports last successful fetch, degraded status
- Visualiser (separate core) reads last good data from DB when Fetcher offline
- Data Health widget displays fetch timestamp, integrity warnings (sourced from batch events)

### Principle VI: Clarity Over Cleverness ✅
- Simple overlap-based stitching (robust median/trimmed mean for scaling factor)
- No complex models; explicit quality flags when weekly substitution used
- Plain-language batch event notes (e.g., "all-zeros for 3 days", "stitching degraded")

### Principle VII: Configuration-as-Code (Single File) ✅
- `config/googili.toml` specifies: keywords, province, schedule time, backfill settings
- Version-controlled; no in-app config UI in MVP
- System logs effective parameters at startup

### Principle VIII: Observability & Data Health ✅
- Structured JSON logs per batch (keywords, rows, quality counts)
- `/healthz` with last fetch timestamp, DB writability probe
- Batch events surfaced in Visualiser's Data Health widget (separate core)

### Principle IX: Equity & Ethical Communication ✅
- Batch event notes include caveats: "RSV is media-sensitive, not disease count"
- Documentation (quickstart.md) emphasizes digital-divide limitations
- No stigmatizing language; honest flagging when data is coarse

### Principle X: User Experience & Accessibility ⚠️ NOT APPLICABLE (Fetcher Core)
- Fetcher is a backend service with no UI
- Visualiser core (separate feature) handles mobile/accessibility requirements
- `/healthz` endpoint returns JSON (machine-readable, not user-facing)

**GATE RESULT**: ✅ PASS - All applicable principles satisfied. Principle X deferred to Visualiser.

## Project Structure

### Documentation (this feature)

```text
specs/001-fetcher-core/
├── plan.md              # This file
├── research.md          # Technology decisions (pytrends, stitching algorithms, WAL mode)
├── data-model.md        # SQLite schema (raw_trenddata, events, config_keywords)
├── quickstart.md        # Operator runbook (Docker setup, cron, backfill, recovery)
├── contracts/
│   └── database-schema.sql   # SQLite DDL with constraints
└── checklists/
    └── requirements.md  # Validation checklist (already complete)
```

### Source Code (repository root)

```text
fetcher/
├── src/
│   ├── models/
│   │   ├── rsv_record.py       # RSV Record domain model
│   │   ├── batch_event.py      # Batch Event domain model
│   │   └── keyword_config.py   # Keyword Configuration model
│   ├── services/
│   │   ├── trends_fetcher.py   # pytrends integration (daily/weekly fetch)
│   │   ├── stitcher.py         # Overlap-based scaling logic
│   │   ├── resampler.py        # Sparse-day policy (3-step fallback)
│   │   ├── ingestion.py        # Orchestrates fetch→stitch→persist→emit
│   │   └── archiver.py         # Monthly CSV snapshots
│   ├── cli/
│   │   └── main.py             # CLI entry (run --daily, backfill --days=N)
│   ├── lib/
│   │   ├── db.py               # SQLite connection, WAL mode, UPSERT helpers
│   │   ├── config.py           # TOML config loader
│   │   ├── logger.py           # Structured JSON logging
│   │   └── health.py           # /healthz HTTP endpoint (Flask/FastAPI)
│   └── __init__.py
├── tests/
│   ├── contract/
│   │   └── test_event_schema.py    # Analyser can read batch events
│   ├── integration/
│   │   └── test_e2e_ingestion.py   # Full daily cycle
│   ├── unit/
│   │   ├── test_stitcher.py        # Scaling factor, outlier handling
│   │   ├── test_resampler.py       # 3-step sparse-day policy
│   │   ├── test_db_upsert.py       # Idempotence
│   │   └── test_windowing.py       # Overlap calculation
│   └── golden/
│       └── test_stitching_scenarios.py  # Known overlap/gap fixtures
├── config/
│   └── googili.toml.example    # Sample config (10 Thai keywords, Chiang Mai TH-50)
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

**Structure Decision**: Single backend service with clear separation between models (domain logic), services (business logic), lib (infrastructure), and CLI (interface). Tests organized by type (unit, integration, contract, golden-file) per constitution TDD requirements.

## Complexity Tracking

> **No violations requiring justification**. All constitution principles satisfied without complexity trade-offs.

## Architecture Decisions

### 1. Google Trends Access: pytrends Library

**Decision**: Use `pytrends` (unofficial Python client for Google Trends)

**Rationale**:
- Most mature Python library for Google Trends access
- Supports daily and weekly granularity requests
- Active maintenance, community support
- **NOTE**: pytrends does NOT automatically retry on HTTP 429 errors - we must implement this

**Alternatives Considered**:
- Official Google Trends API (does not exist for RSV data)
- Direct web scraping (fragile, terms-of-service risk)
- SerpAPI (paid service, unnecessary for MVP)

**Implementation Notes**:
- Wrap pytrends calls in `TrendsFetcher` service with exponential backoff retry for HTTP 429 errors
- **Preventive jitter**: 3-5 second jitter between keyword requests (prevents hitting rate limits)
- **Reactive retry**: Exponential backoff on 429 errors (1min, 5min, 15min) with recovery jitter
- **Exception hierarchy**: RateLimitException (retriable) distinct from PyTrendsException (other errors)
- **Configuration**: Retry behavior configurable in googili.toml (max_retries, backoff_base, backoff_multiplier, max_backoff, respect_retry_after)
- **Batch event handling**: Mark batches as "degraded" (not "fail") when rate limited to distinguish retriable from permanent errors
- **Backfill resilience**: Initial 90-day backfill implements per-date retry to ensure historical data completeness even with intermittent 429 errors
- Log all API errors for operator troubleshooting with 429 errors logged distinctly with structured metadata

### 2. Time-Series Stitching: Overlap-Based Scaling

**Decision**: Compute scaling factor from overlap region using trimmed mean (drop highest/lowest 20%)

**Rationale**:
- Simple, explainable to non-technical analysts
- Down-weights outliers (single-day spikes) without complex statistics
- Preserves zero values (no manufactured signal)
- Literature-supported approach for normalizing independent request windows

**Alternatives Considered**:
- Median (too aggressive for small overlaps)
- Mean (vulnerable to outliers)
- Regression-based (overfitting risk, not explainable)

**Implementation Notes**:
- Minimum overlap: 1 day (warn if overlap < 3 days)
- Scaling factor stored in batch event notes for audit
- If overlap has all zeros, skip scaling (preserve zeros)

### 3. Sparse-Day Resampling: 3-Step Fallback Policy

**Decision**: (1) Re-fetch with wider window → (2) Promote to weekly if ≥3-day run → (3) Mark below_detection if unavailable

**Rationale**:
- "Do not manufacture precision" (constitution ethical principle)
- Honest flagging via granularity/quality columns
- Conservative approach avoids interpolation artifacts
- Operators see clear badges indicating data quality

**Alternatives Considered**:
- Linear interpolation (rejected: manufactures precision)
- Cross-keyword borrowing (rejected: too complex for MVP)
- Leave gaps empty (acceptable, but weekly anchoring adds value)

**Implementation Notes**:
- Coarse records excluded from future stitching factor calculations
- Weekly values anchored to adjacent true_daily days
- Data Health widget shows count of true_daily vs. weekly_flat per batch

### 4. Scheduling: APScheduler In-Container

**Decision**: Use APScheduler inside Docker container with ±3-5 min random jitter

**Rationale**:
- Self-contained (no external cron dependency on host)
- Jitter avoids bursty API calls at exactly 07:30 ICT
- Easier operator setup (just `docker compose up -d`)

**Alternatives Considered**:
- Host cron (viable, requires host configuration)
- Kubernetes CronJob (overkill for single-server MVP)

**Implementation Notes**:
- Target: 07:30 ICT ± random(3-5) minutes
- On startup, check last successful fetch; if >24h ago, trigger 14-day backfill
- APScheduler configured in `cli/main.py` when `--daemon` flag present

### 5. Storage: SQLite with WAL Mode

**Decision**: Single SQLite file with Write-Ahead Logging (WAL) mode

**Rationale**:
- Simple, file-based, no separate DB server needed
- WAL mode allows concurrent reads while Fetcher writes
- Easy to back up (copy single file)
- Sufficient for single-server MVP (~10k records/month)

**Alternatives Considered**:
- PostgreSQL (overkill for MVP, adds deployment complexity)
- CSV files (no ACID, no efficient queries)
- Cloud DB (introduces external dependency, cost)

**Implementation Notes**:
- Enable WAL on first connection: `PRAGMA journal_mode=WAL`
- Unique constraint on (keyword, date) enforces idempotence
- UPSERT on conflict for safe reruns

### 6. Health Endpoint: Lightweight Flask App

**Decision**: Tiny Flask app serving `/healthz` on port 8080

**Rationale**:
- Minimal HTTP server (<50 lines)
- Returns JSON with last fetch timestamp, row counts, DB writability
- Docker healthcheck can curl this endpoint
- Visualiser core can poll for status

**Alternatives Considered**:
- FastAPI (heavier, unnecessary for single endpoint)
- No HTTP (use only logs; rejected: hard for Docker healthcheck)

**Implementation Notes**:
- `/healthz` queries latest batch event, returns 200 OK or 503 degraded
- JSON payload: `{"last_fetch": "2025-11-04T07:32:00+07:00", "rows": 10, "status": "success"}`

## Phase 0: Research Artifacts

*See [research.md](./research.md) for detailed technology decisions and alternatives analysis.*

## Phase 1: Design Artifacts

### Data Model

*See [data-model.md](./data-model.md) for complete entity definitions, relationships, and validation rules.*

**Key Entities**:
- RSV Record: (keyword, date, rsv_raw, rsv_stitched, batch_id, granularity, quality)
- Batch Event: (batch_id, keywords, window, counts, status, timestamps)
- Keyword Configuration: (term, active, created_at)

### Database Contracts

*See [contracts/database-schema.sql](./contracts/database-schema.sql) for DDL with constraints.*

**Tables**:
- `raw_trenddata`: Unique (keyword, date); append-only via UPSERT
- `events_raw_rsv_ingested`: Append-only batch events
- `config_keywords`: Loaded from TOML at startup

### Operator Quickstart

*See [quickstart.md](./quickstart.md) for step-by-step runbook (Docker setup, cron, backfill, recovery).*

**Key Operations**:
- First-time setup: `docker compose up -d` → auto-backfills 90 days
- Daily operation: APScheduler runs at 07:30 ICT ± jitter
- Recovery after outage: `docker exec fetcher python -m googili.fetcher backfill --days=14`
- Health check: `curl http://localhost:8080/healthz`

## Success Metrics (from Spec)

- **SC-001**: Daily RSV data available by 08:00 ICT on 99% of days (constitution timeliness)
- **SC-002**: Zero duplicate (keyword, date) records (UPSERT idempotence)
- **SC-003**: 90-day backfill completes <15 min for 10 keywords
- **SC-004**: Stitched series shows <20% jumps on stable days (stitching quality)
- **SC-005**: 14-day recovery backfill completes <10 min after 72h outage
- **SC-007**: 100% batch events include complete provenance metadata
- **SC-010**: ≥99% fetch success rate per week (operational reliability)

## Risks & Mitigations

**Risk**: Google Trends API changes or rate limits
- **Mitigation**: pytrends library abstracts API; exponential backoff; operator alerts via Data Health widget

**Risk**: Media-driven spikes distort stitching
- **Mitigation**: Trimmed mean down-weights outliers; batch event notes flag unusual patterns

**Risk**: Sparse daily data (≥3-day runs)
- **Mitigation**: 3-step fallback (wider window → weekly anchor → below_detection); honest quality flags

**Risk**: Docker volume mounts fail
- **Mitigation**: Health endpoint probes DB writability; clear error logs; operator runbook includes recovery

**Risk**: Timezone confusion (ICT vs. UTC)
- **Mitigation**: All timestamps explicitly Asia/Bangkok; TZ env var in Docker; documented in quickstart

## Next Steps

1. **Phase 0 Complete**: Research decisions documented (this plan.md + research.md)
2. **Phase 1 Complete**: Design artifacts ready (data-model.md, contracts/, quickstart.md)
3. **Ready for /speckit.tasks**: Generate task breakdown organized by user stories (P1, P2, P3)

**Operator Action Required**: Review quickstart.md and confirm Docker deployment environment before task execution begins.
