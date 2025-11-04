# Research: Fetcher Core Technology Decisions

**Feature**: Fetcher Core - Google Trends RSV Data Ingestion
**Date**: 2025-11-04
**Status**: Complete

## Purpose

This document captures all technology research, alternatives analysis, and final decisions for the Fetcher Core implementation. All decisions align with the Googili constitution v1.1.0 principles.

---

## 1. Google Trends Data Access

### Decision: pytrends (Unofficial Python Client)

**Chosen**: `pytrends` library (https://github.com/GeneralMills/pytrends)

**Rationale**:
- Most mature and actively maintained Python client for Google Trends
- Supports both daily and weekly granularity requests
- Built-in rate limiting and retry logic
- Active community (10k+ stars, regular updates)
- No authentication required for public Trends data
- Handles international characters (Thai keywords) correctly

**Alternatives Considered**:

| Alternative | Pros | Cons | Verdict |
|------------|------|------|---------|
| Official Google Trends API | Sanctioned, stable | **Does not exist** for RSV data | Rejected |
| Direct web scraping | No library dependency | Fragile, TOS violations, hard to maintain | Rejected |
| SerpAPI (paid service) | Reliable, official | Monthly cost, overkill for MVP | Deferred |
| trendet library | Alternative Python client | Less mature, fewer features | Rejected |

**Implementation Details**:
- Wrap pytrends in `TrendsFetcher` service with exponential backoff
- Rate limiting: 3-5 second jitter between keyword requests to avoid blocking
- Error handling: Log all pytrends exceptions with context for operator troubleshooting
- Geographic scope: Use `geo='TH-50'` for Chiang Mai Province

**Testing Strategy**:
- Unit tests: Mock pytrends responses for predictable testing
- Integration tests: Optional live API tests (skipped in CI; run manually)
- Contract tests: Verify pytrends output format matches expected schema

**References**:
- pytrends Documentation: https://pypi.org/project/pytrends/
- Google Trends Terms: https://trends.google.com/trends/terms

---

## 2. Time-Series Stitching Algorithm

### Decision: Overlap-Based Scaling with Trimmed Mean

**Chosen**: Compute scaling factor from overlap region using trimmed mean (drop highest/lowest 20%)

**Rationale**:
- Simple, explainable to non-technical public health analysts (constitution Principle VI: Clarity Over Cleverness)
- Robust to outliers (single-day spikes) without requiring complex statistical models
- Preserves zero values (no manufactured signal, per constitution ethical principles)
- Literature-supported: Referenced in Google Flu Trends post-mortem and academic papers on web search surveillance

**Mathematical Approach**:
```
For overlapping days d1, d2, ..., dn:
  old_values = [existing stitched RSV for d1...dn]
  new_values = [new raw RSV for d1...dn]

  ratios = [old_values[i] / new_values[i] for i in range(n) if new_values[i] > 0]
  trimmed_ratios = drop highest & lowest 20% of ratios
  scaling_factor = mean(trimmed_ratios)

  stitched_new = new_raw * scaling_factor
```

**Alternatives Considered**:

| Alternative | Pros | Cons | Verdict |
|------------|------|------|---------|
| Simple mean | Easy to understand | Vulnerable to outliers | Rejected |
| Median | Robust to outliers | Too aggressive for small overlaps (<5 days) | Rejected |
| Weighted least squares | Optimal for large overlaps | Not explainable; overkill for MVP | Deferred |
| No stitching (use raw) | Simple | Creates normalization artifacts, unusable for trends | Rejected |

**Implementation Details**:
- Minimum overlap: 1 day (warn operators if <3 days)
- Store scaling factor in batch event notes for audit trail
- If overlap contains all zeros, skip scaling (preserve zeros)
- If new window has no overlap, log integrity warning and store unstitched (alert operators)

**Testing Strategy**:
- Golden-file tests: Known overlap scenarios (normal, outlier-heavy, all-zeros)
- Property tests: Verify stitched series has smoother transitions than raw
- Unit tests: Edge cases (single-day overlap, negative values, NaN handling)

**References**:
- "The Parable of Google Flu" (Lazer et al., 2014): Discusses normalization challenges
- "Nowcasting" approaches in epidemiological surveillance literature

---

## 3. Sparse-Day Resampling Policy

### Decision: 3-Step Conservative Fallback

**Chosen**: (1) Re-fetch with wider window → (2) Promote to weekly if ≥3-day run → (3) Mark below_detection

**Rationale**:
- **"Do not manufacture precision"** (constitution ethical principle)
- Honest flagging via `granularity` and `quality` columns preserves data integrity
- Conservative approach avoids interpolation artifacts that could mislead analysts
- Weekly anchoring adds value for operational use while being transparent about coarseness

**Step-by-Step Policy**:

**Step 1: Re-fetch with Wider Window**
- If daily data missing for date D, expand request window to D ± 7 days
- Increases chance of Google Trends returning daily granularity
- If successful, mark `granularity=daily`, `quality=true`

**Step 2: Promote to Weekly (if ≥3-day run)**
- If re-fetch still fails AND ≥3 consecutive missing days detected
- Request weekly RSV for that week
- Anchor weekly value to adjacent true_daily days using overlap scaling
- Assign same weekly-anchored value to all days in that week (flat profile)
- Mark `granularity=weekly`, `impute_method=weekly_flat`, `quality=coarse`
- **Exclude from future stitching**: Coarse rows not used for scaling factor calculation

**Step 3: Mark Below Detection**
- If weekly data also unavailable or all-zero
- Leave days unpublished (NULL in rsv_stitched column)
- Raise Data Health warning: `status=below_detection`
- Log in batch event notes for operator visibility

**Alternatives Considered**:

| Alternative | Pros | Cons | Verdict |
|------------|------|------|---------|
| Linear interpolation | Smooth series | **Manufactures precision**; violates constitution | Rejected |
| Cross-keyword borrowing | Fills more gaps | Too complex; domain assumptions | Rejected |
| Leave gaps empty | Simple, honest | Loses operational value | Acceptable but enhanced by Step 2 |
| Forward-fill previous day | Simple | Misleading; assumes no change | Rejected |

**Implementation Details**:
- Minimum run length for weekly promotion: 3 days (configurable in constitution review)
- Single isolated missing days NOT promoted to weekly; left NULL
- Coarse records flagged in Data Health widget with distinct badge color
- Batch events include counts: `true_daily_count`, `weekly_flat_count`, `missing_count`

**Testing Strategy**:
- Unit tests: 3-day run triggers weekly, 2-day run does not
- Integration tests: End-to-end sparse scenario (missing → re-fetch → weekly → store)
- Golden-file tests: Known sparse patterns (isolated gaps, long runs, all-unavailable)

**References**:
- Constitution Principle I: "Do not manufacture precision"
- WHO surveillance guidelines: Transparency about data limitations

---

## 4. Job Scheduling

### Decision: APScheduler In-Container with Jitter

**Chosen**: APScheduler library running inside Docker container with ±3-5 minute random jitter

**Rationale**:
- Self-contained: No external cron dependency on host system
- Jitter prevents bursty API calls at exactly 07:30 ICT (reduces rate-limit risk)
- Simpler operator setup: `docker compose up -d` handles everything
- Programmatic control: Easy to implement recovery logic (check last fetch; trigger backfill if >24h)

**Configuration**:
```python
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import random

scheduler = BlockingScheduler()
jitter = random.randint(3, 5)  # minutes

scheduler.add_job(
    func=run_daily_ingestion,
    trigger=CronTrigger(hour=7, minute=30 + jitter, timezone='Asia/Bangkok'),
    id='daily_fetch',
    replace_existing=True
)
```

**Alternatives Considered**:

| Alternative | Pros | Cons | Verdict |
|------------|------|------|---------|
| Host cron | Standard Unix tool | Requires host config; no programmatic jitter | Viable alternative |
| Kubernetes CronJob | Cloud-native | Overkill for single-server MVP | Deferred |
| Systemd timers | Linux-native | Requires host config; less portable | Rejected |
| Cloud scheduler (AWS EventBridge) | Managed service | Vendor lock-in; cost | Deferred |

**Implementation Details**:
- Scheduler runs in `cli/main.py` when `--daemon` flag present
- On container startup: Check last successful fetch timestamp
  - If >24 hours ago: Trigger 14-day recovery backfill before resuming daily schedule
  - Else: Wait for next scheduled run
- Graceful shutdown: `SIGTERM` handler flushes logs and closes DB connection
- Health endpoint includes next scheduled run time

**Testing Strategy**:
- Unit tests: Mock time; verify jitter applied correctly
- Integration tests: Verify recovery backfill triggers after simulated outage
- Manual tests: Observe actual schedule in staging environment

**References**:
- APScheduler Documentation: https://apscheduler.readthedocs.io/
- Constitution Performance Goal: Daily ingestion by 07:30 ICT

---

## 5. Data Storage

### Decision: SQLite with WAL Mode

**Chosen**: Single SQLite database file with Write-Ahead Logging (WAL) enabled

**Rationale**:
- **Simplicity**: File-based, no separate DB server, easy backups (copy file)
- **WAL mode**: Allows concurrent reads (Visualiser, Analyser) while Fetcher writes
- **ACID guarantees**: Transactions ensure data integrity even on crashes
- **Sufficient scale**: 10 keywords × 90+ days × 3 tables = ~10k records/month (well within SQLite limits)
- **Constitution alignment**: Single file fits "simplicity & reversibility" principle

**WAL Mode Benefits**:
- Readers never blocked by writers (critical for Visualiser fail-safe operation)
- Better concurrency than default rollback journal
- Crash recovery: WAL log replays on next connection

**Schema Strategy**:
- Unique constraint on `(keyword, date)` in `raw_trenddata` enforces idempotence
- UPSERT (`INSERT OR REPLACE`) allows safe reruns after failures
- Append-only `events_raw_rsv_ingested` table for audit trail
- Indexes on `batch_id`, `fetched_at_ict` for query performance

**Alternatives Considered**:

| Alternative | Pros | Cons | Verdict |
|------------|------|------|---------|
| PostgreSQL | Enterprise features, better concurrency | Requires separate server; deployment complexity | Deferred post-MVP |
| CSV files | Simple, portable | No ACID, no efficient queries, no constraints | Rejected |
| Cloud DB (RDS, Firestore) | Managed service | Vendor lock-in, cost, latency | Deferred |
| DuckDB | Fast analytics | Newer, less mature for write-heavy workloads | Watch for future |

**Implementation Details**:
- Enable WAL on first connection: `PRAGMA journal_mode=WAL`
- Connection pooling: Single connection per Fetcher instance (no concurrency within Fetcher)
- Backup strategy: Daily file copy to `./archive` before monthly snapshot
- Migration path: SQLite → PostgreSQL documented for scale-out (10x keywords, multi-province)

**Testing Strategy**:
- Unit tests: Verify UPSERT idempotence (run same batch twice, no duplicates)
- Integration tests: Concurrent reads (mock Visualiser) during Fetcher write
- Crash tests: Kill Fetcher mid-transaction, verify DB consistency on restart

**References**:
- SQLite WAL Documentation: https://www.sqlite.org/wal.html
- Constitution Principle: "SQLite with WAL" explicitly recommended

---

## 6. Health Endpoint

### Decision: Lightweight Flask App on Port 8080

**Chosen**: Minimal Flask application serving `/healthz` JSON endpoint

**Rationale**:
- **Minimal overhead**: Flask lightweight for single-endpoint use case (<50 lines)
- **Docker healthcheck**: `curl http://localhost:8080/healthz` in container health probe
- **Visualiser integration**: Polling endpoint provides Fetcher status without DB dependency
- **Observability**: Returns last fetch timestamp, row counts, DB writability

**Endpoint Spec**:
```
GET /healthz
Response 200 OK (healthy):
{
  "status": "success",
  "last_fetch": "2025-11-04T07:32:15+07:00",
  "last_batch_id": "batch_20251104_073215",
  "rows_written": 10,
  "true_daily": 9,
  "weekly_flat": 1,
  "missing": 0,
  "db_writable": true
}

Response 503 Service Unavailable (degraded):
{
  "status": "degraded",
  "last_fetch": "2025-11-02T07:30:00+07:00",  # >24h ago
  "error": "No successful fetch in 48 hours"
}
```

**Alternatives Considered**:

| Alternative | Pros | Cons | Verdict |
|------------|------|------|---------|
| FastAPI | Modern, OpenAPI docs | Heavier (uvicorn, pydantic); overkill for 1 endpoint | Deferred |
| No HTTP (logs only) | Simplest | Hard for Docker healthcheck; Visualiser can't poll | Rejected |
| Embedded in CLI | No separate server | Blocks CLI; harder to test | Rejected |

**Implementation Details**:
- Flask runs in separate thread from scheduler (non-blocking)
- Health checks query latest `events_raw_rsv_ingested` row
- DB writability: Attempt `INSERT INTO health_probe (timestamp) VALUES (NOW())`; rollback
- Timeout: 3-second query timeout; return 503 if DB locked

**Testing Strategy**:
- Unit tests: Mock DB responses; verify JSON structure
- Integration tests: Start Flask app, curl `/healthz`, verify response
- Load tests: 100 concurrent `/healthz` requests (verify no contention with Fetcher writes)

**References**:
- Constitution Principle VIII: "/healthz endpoints per core"
- Docker healthcheck docs: https://docs.docker.com/engine/reference/builder/#healthcheck

---

## 7. Logging & Observability

### Decision: Structured JSON Logging with Python `logging` Module

**Chosen**: Python `logging` module configured for structured JSON output

**Rationale**:
- **Structured logs**: JSON format parseable by log aggregators (future ELK/Loki integration)
- **Standard library**: No external dependency for basic logging
- **Constitution alignment**: "Structured logging (JSON) for ingestion, analysis, errors"

**Log Format**:
```json
{
  "timestamp": "2025-11-04T07:32:15+07:00",
  "level": "INFO",
  "logger": "googili.fetcher.ingestion",
  "message": "Batch ingestion complete",
  "batch_id": "batch_20251104_073215",
  "keywords": ["ไข้", "ไอ", "เจ็บคอ"],
  "rows_written": 10,
  "true_daily": 9,
  "weekly_flat": 1,
  "duration_seconds": 42.3
}
```

**Log Levels**:
- **DEBUG**: Detailed pytrends calls, stitching calculations
- **INFO**: Batch start/end, summary stats
- **WARNING**: Stitching degraded, sparse data promoted to weekly
- **ERROR**: pytrends failures, DB write errors
- **CRITICAL**: Fatal errors preventing ingestion

**Alternatives Considered**:

| Alternative | Pros | Cons | Verdict |
|------------|------|------|---------|
| python-json-logger | Cleaner JSON formatting | External dependency | Consider if formatting issues arise |
| structlog | Rich features, best-in-class | Heavy; overkill for MVP | Deferred |
| Plain text logs | Simple | Not parseable by log aggregators | Rejected |

**Implementation Details**:
- Log rotation: Daily rotation, keep 30 days (handled by Docker volume or host logrotate)
- Sensitive data: Never log Thai search terms in production (config-driven debug flag)
- Context: Include `batch_id` in all logs within a batch operation
- Output: `stdout` (Docker captures); optionally file for local debugging

**Testing Strategy**:
- Unit tests: Verify log messages produced at expected levels
- Integration tests: Parse JSON logs, validate structure
- Manual review: Inspect logs during staging runs for clarity

**References**:
- Python logging docs: https://docs.python.org/3/library/logging.html
- Constitution Principle VIII: "Structured logging (JSON)"

---

## 8. Configuration Management

### Decision: TOML Configuration File

**Chosen**: Single `config/googili.toml` file with version control

**Rationale**:
- **Human-readable**: TOML simpler than JSON/YAML for operators
- **Version-controlled**: Git tracks all config changes (constitution audit requirement)
- **Single file**: All settings in one place (keywords, schedule, thresholds)
- **Python support**: Built-in `tomllib` in Python 3.11+

**Config Structure**:
```toml
[general]
province = "TH-50"  # Chiang Mai
timezone = "Asia/Bangkok"

[keywords]
terms = [
  "ไข้",      # Fever
  "ไอ",       # Cough
  "เจ็บคอ",   # Sore throat
  # ... 7 more keywords
]

[schedule]
daily_time = "07:30"
jitter_minutes = [3, 5]
backfill_on_startup_if_gap_hours = 24

[backfill]
initial_days = 90
recovery_days = 14

[stitching]
min_overlap_days = 1
trim_percent = 20  # Drop highest/lowest 20% for scaling factor

[resampling]
min_run_for_weekly = 3  # ≥3 consecutive missing days triggers weekly promotion

[archive]
output_dir = "./data/archive"
cadence = "monthly"

[health]
port = 8080
db_probe_timeout_seconds = 3
```

**Alternatives Considered**:

| Alternative | Pros | Cons | Verdict |
|------------|------|------|---------|
| YAML | More features (anchors, etc.) | More complex; YAML security issues | Rejected |
| JSON | Universal | Not human-friendly; no comments | Rejected |
| Environment variables | 12-factor app pattern | Hard to manage 10+ keywords; no versioning | Rejected |
| Database config | UI-editable | Violates constitution "config-as-code" principle | Rejected |

**Implementation Details**:
- Load config at startup: `import tomllib; config = tomllib.load(f)`
- Validation: Pydantic models for type checking and defaults
- Effective parameters logged at startup for reproducibility
- Changes require container restart (intentional; encourages git commits)

**Testing Strategy**:
- Unit tests: Valid TOML loads correctly; invalid TOML raises clear error
- Integration tests: Override config path via env var for test fixtures
- Schema validation: Pydantic ensures required fields present

**References**:
- TOML specification: https://toml.io/en/
- Constitution Principle VII: "Configuration-as-code (single file)"

---

## 9. Containerization & Deployment

### Decision: Docker + Docker Compose for Single-Server MVP

**Chosen**: Dockerfile with multi-stage build; `docker-compose.yml` for orchestration

**Rationale**:
- **Portability**: Runs on any Linux server with Docker installed
- **Reproducible builds**: Pinned Python 3.11-slim base image
- **Simple deployment**: `docker compose up -d` for operators
- **Volume mounts**: Persist DB and config outside container

**Dockerfile Strategy**:
```dockerfile
FROM python:3.11-slim AS base
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM base AS runtime
COPY src/ ./src/
ENV TZ=Asia/Bangkok
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "googili.fetcher", "run", "--daemon"]
```

**docker-compose.yml**:
```yaml
services:
  fetcher:
    build: ./fetcher
    container_name: googili_fetcher
    environment:
      - TZ=Asia/Bangkok
      - LOG_LEVEL=INFO
    volumes:
      - ./data:/app/data          # SQLite + archives
      - ./config:/app/config      # googili.toml
    ports:
      - "8080:8080"  # /healthz endpoint
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8080/healthz"]
      interval: 30s
      timeout: 3s
      retries: 3
    restart: unless-stopped
    networks:
      - googili_net

networks:
  googili_net:
    driver: bridge
```

**Alternatives Considered**:

| Alternative | Pros | Cons | Verdict |
|------------|------|------|---------|
| Kubernetes | Scalable, cloud-native | Overkill for single-server MVP | Deferred |
| Systemd service | Native Linux | Harder dependency management | Rejected |
| Bare metal Python | No container overhead | Harder to replicate environment | Rejected |

**Implementation Details**:
- Multi-stage build: Separate build/runtime stages for smaller image
- Health probe: Docker restarts container if `/healthz` fails 3 times
- Volume mounts: `./data` and `./config` on host for persistence
- Network: Bridge network `googili_net` for future Analyser/Visualiser communication

**Testing Strategy**:
- Build tests: `docker build` succeeds; image size < 200MB
- Compose tests: `docker compose up` starts healthy container
- Volume tests: Create file in container; verify visible on host

**References**:
- Docker best practices: https://docs.docker.com/develop/dev-best-practices/
- User-provided plan: Docker+compose architecture

---

## Summary of Decisions

| Component | Decision | Key Rationale |
|-----------|----------|---------------|
| **Google Trends Access** | pytrends library | Mature, active, supports daily/weekly granularity |
| **Stitching** | Trimmed mean overlap scaling | Robust to outliers, explainable, constitution-aligned |
| **Resampling** | 3-step fallback (re-fetch → weekly → below_detection) | Honest about precision, avoids interpolation |
| **Scheduling** | APScheduler in-container | Self-contained, jitter support, recovery logic |
| **Storage** | SQLite + WAL | Simple, concurrent-read friendly, ACID guarantees |
| **Health** | Flask /healthz endpoint | Lightweight, Docker-compatible, Visualiser-compatible |
| **Logging** | Structured JSON (Python logging) | Parseable, constitution-mandated |
| **Config** | TOML single file | Human-readable, version-controlled |
| **Deployment** | Docker + Compose | Portable, operator-friendly, MVP-appropriate |

All decisions align with Googili constitution v1.1.0 and prioritize simplicity, explainability, and operational reliability for public health surveillance.
