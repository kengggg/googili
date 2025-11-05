# Technology Research: Fetcher Core

**Feature**: Fetcher Core - Google Trends RSV Data Ingestion
**Date**: 2025-11-04
**Purpose**: Document technology decisions and alternatives considered for MVP implementation

---

## Decision 1: Google Trends Access Method

### Problem Statement
Need reliable access to Google Trends Relative Search Volume (RSV) data for Thai keywords scoped to Chiang Mai Province (TH-50), supporting both daily and weekly granularity requests.

### Options Evaluated

#### Option A: pytrends (Unofficial Python Client) ✅ SELECTED
**Description**: Community-maintained Python library wrapping Google Trends web interface

**Pros**:
- Most mature Python library for Google Trends (5000+ GitHub stars, active maintenance)
- Supports all required features: daily/weekly granularity, geographic scoping, timeframe specification
- Handles rate limiting, cookie management, and retry logic internally
- Extensive community documentation and troubleshooting resources
- MIT licensed, permissive

**Cons**:
- Unofficial API; breaks if Google changes web interface structure
- Rate limiting not officially documented (community-learned thresholds)
- No SLA or support from Google

**Implementation Notes**:
```python
from pytrends.request import TrendReq
pytrends = TrendReq(hl='th-TH', tz=420)  # Thai locale, ICT timezone
pytrends.build_payload(['ไข้'], cat=0, timeframe='2025-01-01 2025-01-30', geo='TH-50', gprop='')
df = pytrends.interest_over_time()
```

#### Option B: Direct Web Scraping
**Description**: Parse Google Trends HTML responses directly using BeautifulSoup or Scrapy

**Pros**:
- Full control over request logic
- No third-party dependency

**Cons**:
- Fragile; breaks on any UI change
- Terms of Service concerns (automated scraping)
- Must implement rate limiting, cookie management, captcha handling
- High maintenance burden

**Rejected**: Too fragile and high-risk for operational surveillance system.

#### Option C: SerpAPI (Commercial Service)
**Description**: Paid API service providing structured Google Trends data

**Pros**:
- Stable, documented API
- Handles rate limits and compliance
- SLA guarantees

**Cons**:
- Monthly cost ($50-250 depending on volume)
- External dependency/vendor lock-in
- Overkill for MVP with 10 keywords

**Rejected**: Unnecessary cost and complexity for MVP; consider post-pilot if pytrends proves unstable.

### Decision
**Use pytrends** with defensive error handling and fallback policies documented in batch event notes.

**Validation Criteria**:
- ≥99% fetch success rate during 6-month pilot
- Median fetch latency <30 seconds per keyword

---

## Decision 2: Time-Series Stitching Algorithm

### Problem Statement
Google Trends normalizes each request window independently (0-100 scale relative to window's peak). Concatenating raw values creates artificial level jumps. Need robust stitching to produce continuous, comparable time series.

### Options Evaluated

#### Option A: Trimmed Mean Overlap Scaling ✅ SELECTED
**Description**: Compute scaling factor from overlap region using trimmed mean (drop highest/lowest 20%)

**Pros**:
- Simple, explainable algorithm (suitable for non-technical stakeholders)
- Down-weights single-day outliers without complex statistics
- Preserves zeros (no manufactured signal)
- Robust to small sample sizes (≥1 day overlap)
- Literature-supported: used in time series normalization (Hyndman & Athanasopoulos, 2018)

**Cons**:
- Requires ≥1 day overlap between consecutive windows
- Less statistically efficient than regression for large overlaps

**Implementation Notes**:
```python
import numpy as np
from scipy.stats import trim_mean

def compute_scaling_factor(old_window_overlap, new_window_overlap):
    # Trim 20% from each tail
    old_trimmed = trim_mean(old_window_overlap, proportiontocut=0.2)
    new_trimmed = trim_mean(new_window_overlap, proportiontocut=0.2)

    if new_trimmed == 0:
        return 1.0  # Avoid division by zero; preserve zeros

    return old_trimmed / new_trimmed
```

#### Option B: Median Scaling
**Description**: Use median of overlap ratios as scaling factor

**Pros**:
- Simple, robust to extreme outliers
- Requires minimal overlap data

**Cons**:
- Too aggressive for small overlaps (≤3 days)
- Discards tail information that may be relevant

**Rejected**: Trimmed mean provides better balance for typical 7-day overlaps.

#### Option C: Linear Regression
**Description**: Fit linear model to overlap points, use slope as scaling factor

**Pros**:
- Statistically efficient for large overlaps
- Can detect and adjust for trends

**Cons**:
- Overfitting risk with small overlaps (<5 days)
- Difficult to explain to non-technical users
- Assumes linear relationship (not always true for media-driven spikes)

**Rejected**: Too complex for MVP; consider post-pilot if trimmed mean shows systematic bias.

### Decision
**Use trimmed mean (20% trim)** with minimum 1-day overlap requirement.

**Validation Criteria**:
- Stitched series shows <20% jumps on consecutive stable days
- Golden-file tests with known overlap scenarios pass

---

## Decision 3: Sparse-Day Resampling Policy

### Problem Statement
Google Trends sometimes returns no daily data for low-volume keywords on specific days. Need policy to fill gaps without manufacturing false precision.

### Options Evaluated

#### Option A: 3-Step Fallback (Re-fetch → Weekly → Below Detection) ✅ SELECTED
**Description**:
1. Re-fetch with wider window (e.g., 30→90 days) to see if daily data becomes available
2. If ≥3 consecutive days missing, promote to weekly granularity (flat imputation)
3. If weekly unavailable, mark as `below_detection` (no value)

**Pros**:
- Honest flagging via granularity/quality metadata
- Avoids interpolation artifacts (constitution ethical principle: no manufactured precision)
- Conservative approach preserves trust
- Analysts see explicit "coarse" badges for weekly-derived days

**Cons**:
- Introduces gaps in time series
- Weekly values less precise than daily

**Implementation Notes**:
- Store impute_method='weekly_flat', quality='coarse' for promoted days
- Exclude coarse records from future stitching calculations
- Data Health widget shows count breakdown (true_daily, weekly_flat, missing)

#### Option B: Linear Interpolation
**Description**: Fill gaps by linearly interpolating between adjacent days

**Pros**:
- No gaps in time series
- Smooth transitions

**Cons**:
- Manufactures precision where none exists (violates constitution principle)
- Can create misleading trends (e.g., interpolating through sudden spike)
- Analysts cannot distinguish real vs. imputed data

**Rejected**: Unacceptable for public health surveillance; integrity over completeness.

#### Option C: Cross-Keyword Borrowing
**Description**: Use correlated keywords to estimate missing values

**Pros**:
- Leverages domain knowledge (symptom co-occurrence)

**Cons**:
- Too complex for MVP
- Assumes stable cross-keyword correlations (not validated)
- Requires correlation matrix maintenance

**Rejected**: Defer to future research phase; MVP uses simpler fallback.

### Decision
**Use 3-step fallback policy** with explicit quality flagging.

**Validation Criteria**:
- ≥90% of days have true_daily quality during pilot
- Operators rate data transparency as "high" on feasibility survey

---

## Decision 4: Scheduling Mechanism

### Problem Statement
Need daily ingestion at 07:30 ICT with jitter to avoid API rate limit clustering. Deployment on single Linux server.

### Options Evaluated

#### Option A: APScheduler In-Container ✅ SELECTED
**Description**: Python scheduling library running inside Docker container

**Pros**:
- Self-contained (no external dependencies)
- Random jitter easily implemented (±3-5 minutes)
- Easier operator setup (`docker compose up -d`)
- Works on any host OS (cross-platform)
- No host cron configuration needed

**Cons**:
- Scheduler dies if container crashes (mitigated by Docker restart policy)
- Less familiar to traditional sysadmins

**Implementation Notes**:
```python
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
import random

scheduler = BlockingScheduler(timezone='Asia/Bangkok')

def daily_fetch_with_jitter():
    jitter_seconds = random.randint(180, 300)  # 3-5 minutes
    time.sleep(jitter_seconds)
    run_ingestion()

scheduler.add_job(daily_fetch_with_jitter, CronTrigger(hour=7, minute=30))
scheduler.start()
```

#### Option B: Host Cron
**Description**: Use host system's cron to trigger Docker exec command

**Pros**:
- Standard Unix scheduling mechanism
- Survives container restarts
- Familiar to operators

**Cons**:
- Requires host configuration (not containerized)
- Harder to implement jitter (requires separate script)
- Platform-dependent (Linux/macOS only)

**Rejected**: Prefer containerized solution for portability.

#### Option C: Kubernetes CronJob
**Description**: Use Kubernetes-native CronJob resource

**Pros**:
- Cloud-native, scalable
- Built-in job history and retry policies

**Cons**:
- Requires K8s infrastructure (overkill for single-server MVP)
- Added operational complexity
- Cost overhead

**Rejected**: Too heavy for MVP; consider post-pilot if scaling beyond single server.

### Decision
**Use APScheduler in-container** with Docker restart policy `unless-stopped`.

**Validation Criteria**:
- Daily ingestion executes within 10 minutes of 07:30 ICT on 99% of days
- Automatic 14-day backfill triggers on startup after >24h gap

---

## Decision 5: Data Storage Layer

### Problem Statement
Need ACID-compliant storage for RSV records and batch events with concurrent read support (Visualiser queries while Fetcher writes).

### Options Evaluated

#### Option A: SQLite with WAL Mode ✅ SELECTED
**Description**: File-based SQLite database with Write-Ahead Logging enabled

**Pros**:
- Zero-setup (no separate server)
- WAL mode allows concurrent reads during writes
- ACID guarantees with transactions
- Easy backup (copy single file)
- Sufficient performance for ~10k records/month
- Built-in to Python (no external dependencies)

**Cons**:
- Single-writer limitation (acceptable: only Fetcher writes)
- Not suitable for horizontal scaling (defer to PostgreSQL post-pilot)

**Implementation Notes**:
```python
import sqlite3
conn = sqlite3.connect('googili.db')
conn.execute('PRAGMA journal_mode=WAL')  # Enable WAL
conn.execute('PRAGMA foreign_keys=ON')   # Enforce FK constraints
```

#### Option B: PostgreSQL
**Description**: Full-featured relational database server

**Pros**:
- Multi-writer support
- Better performance at scale
- Advanced features (partitioning, replication)

**Cons**:
- Requires separate server deployment
- Added operational overhead (connection pooling, backups)
- Overkill for single-server MVP
- Resource overhead (memory, CPU)

**Rejected**: Unnecessary complexity for MVP; migrate post-pilot if needed.

#### Option C: CSV Files
**Description**: Store records as CSV files on filesystem

**Pros**:
- Simple, human-readable
- No database dependencies

**Cons**:
- No ACID guarantees
- No efficient querying (must scan entire file)
- No referential integrity
- Concurrency issues

**Rejected**: Insufficient for operational system; only suitable for archives.

### Decision
**Use SQLite with WAL mode** for MVP; document migration path to PostgreSQL.

**Validation Criteria**:
- Zero database corruption incidents during pilot
- Query response time <100ms for Visualiser data requests
- Concurrent read/write tested under load

---

## Decision 6: Health Endpoint Implementation

### Problem Statement
Need lightweight HTTP endpoint for Docker healthcheck and Visualiser polling, returning last fetch status and DB writability.

### Options Evaluated

#### Option A: Flask Microservice ✅ SELECTED
**Description**: Minimal Flask app serving single `/healthz` endpoint

**Pros**:
- Lightweight (<50 lines)
- Familiar to Python developers
- Built-in development server sufficient for single endpoint
- Easy to extend post-MVP

**Cons**:
- Development server not production-hardened (acceptable for internal endpoint)

**Implementation Notes**:
```python
from flask import Flask, jsonify
import sqlite3

app = Flask(__name__)

@app.route('/healthz')
def health():
    try:
        conn = sqlite3.connect('googili.db', timeout=3)
        cursor = conn.execute('SELECT * FROM v_latest_batch LIMIT 1')
        batch = cursor.fetchone()
        conn.close()

        if batch:
            return jsonify({'status': 'success', 'last_fetch': batch[2], 'rows': batch[3]}), 200
        else:
            return jsonify({'status': 'degraded', 'message': 'No batches found'}), 200
    except Exception as e:
        return jsonify({'status': 'fail', 'error': str(e)}), 503

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

#### Option B: FastAPI
**Description**: Modern async Python framework

**Pros**:
- Auto-generated OpenAPI docs
- Type validation with Pydantic
- Better performance (async)

**Cons**:
- Heavier dependency chain
- Overkill for single synchronous endpoint
- Added complexity for MVP

**Rejected**: Unnecessary features for simple healthcheck.

#### Option C: No HTTP Endpoint (Logs Only)
**Description**: Rely solely on structured logs for health monitoring

**Pros**:
- No additional service needed

**Cons**:
- Docker healthcheck requires HTTP endpoint
- Harder for Visualiser to poll status
- No machine-readable status

**Rejected**: HTTP endpoint required for operational visibility.

### Decision
**Use Flask microservice** on port 8080 for `/healthz`.

**Validation Criteria**:
- Endpoint responds <100ms (99th percentile)
- Docker healthcheck passes when Fetcher operational
- Returns 503 when DB inaccessible or last fetch >48h ago

---

## Decision 7: Logging Strategy

### Problem Statement
Need structured logs for troubleshooting, governance audits, and operational monitoring. Logs must include batch metadata, fetch errors, and quality warnings.

### Options Evaluated

#### Option A: Structured JSON Logging ✅ SELECTED
**Description**: Use Python `logging` with JSON formatter (e.g., `python-json-logger`)

**Pros**:
- Machine-parsable (ingestible by ELK, Loki, CloudWatch)
- Consistent schema across log entries
- Easy to filter/aggregate (e.g., "all ERROR level logs")
- Supports nested metadata (batch_id, keywords, row counts)

**Cons**:
- Less human-readable in raw form (mitigated by `jq` or log viewer)

**Implementation Notes**:
```python
import logging
from pythonjsonlogger import jsonlogger

logger = logging.getLogger()
logHandler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter('%(asctime)s %(name)s %(levelname)s %(message)s')
logHandler.setFormatter(formatter)
logger.addHandler(logHandler)

logger.info('Daily ingestion started', extra={
    'batch_id': 'batch_20251104_073215',
    'keywords': ['ไข้', 'ไอ'],
    'window': '2025-11-03 to 2025-11-04'
})
```

#### Option B: Plain Text Logging
**Description**: Standard Python logging with text format

**Pros**:
- Human-readable
- No additional dependencies

**Cons**:
- Hard to parse/aggregate
- Inconsistent structure

**Rejected**: Insufficient for operational system requiring log aggregation.

### Decision
**Use structured JSON logging** with `python-json-logger`.

**Validation Criteria**:
- All batch events logged with complete metadata
- Operators can filter logs by batch_id, status, keyword
- Log retention: 30 days (Docker log rotation)

---

## Decision 8: Configuration Management

### Problem Statement
Need single source of truth for operational parameters (keywords, province, schedule, backfill settings) that is version-controlled and requires no in-app UI.

### Options Evaluated

#### Option A: TOML Configuration File ✅ SELECTED
**Description**: Single `config/googili.toml` file with all parameters

**Pros**:
- Human-readable, supports comments
- Native Python support via `tomli` (stdlib in 3.11+)
- Type-safe (ints, bools, arrays)
- Version-controlled (Git)
- Explicit parameter names (self-documenting)

**Cons**:
- Requires container restart to reload (acceptable for MVP)

**Implementation Notes**:
```toml
[general]
province = "TH-50"
timezone = "Asia/Bangkok"

[keywords]
terms = ["ไข้", "ไอ", "เจ็บคอ"]

[schedule]
daily_time = "07:30"
jitter_minutes = [3, 5]

[backfill]
initial_days = 90
recovery_days = 14
```

#### Option B: YAML
**Description**: YAML configuration file

**Pros**:
- Human-readable
- Widely used

**Cons**:
- Less type-safe (implicit type coercion)
- No native Python support (requires `PyYAML`)
- Indentation-sensitive (error-prone)

**Rejected**: TOML clearer and stdlib-supported in Python 3.11+.

#### Option C: Environment Variables
**Description**: Pass all config via env vars or .env file

**Pros**:
- 12-factor app pattern
- Easy to override in Docker

**Cons**:
- Verbose for complex structures (arrays of keywords)
- No comments or documentation inline
- Hard to version-control complex configs

**Rejected**: Too limited for structured keyword lists.

### Decision
**Use TOML configuration file** at `config/googili.toml`.

**Validation Criteria**:
- All parameters documented inline via comments
- System logs effective config at startup
- Config changes require explicit restart (logged in batch event)

---

## Decision 9: Deployment & Orchestration

### Problem Statement
Need reproducible deployment for Linux server with minimal operator setup. Target: single-command startup.

### Options Evaluated

#### Option A: Docker + Docker Compose ✅ SELECTED
**Description**: Containerized service defined in `docker-compose.yml`

**Pros**:
- Single-command setup: `docker compose up -d`
- Reproducible environment (Python 3.11, dependencies locked)
- Easy volume mounts for data persistence
- Built-in healthcheck support
- Restart policies (`unless-stopped`)
- Works on any Linux/macOS/Windows host

**Cons**:
- Requires Docker installed on host
- Single-server limitation (no orchestration)

**Implementation Notes**:
```yaml
services:
  fetcher:
    build: ./fetcher
    container_name: googili_fetcher
    environment:
      - TZ=Asia/Bangkok
      - LOG_LEVEL=INFO
    volumes:
      - ./data:/app/data
      - ./config:/app/config:ro
    ports:
      - "8080:8080"
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8080/healthz"]
      interval: 30s
      timeout: 3s
      retries: 3
    restart: unless-stopped
```

#### Option B: Kubernetes
**Description**: Deploy as K8s Deployment with CronJob

**Pros**:
- Production-grade orchestration
- Scalable, self-healing
- Advanced scheduling

**Cons**:
- Requires K8s cluster (overkill for single-server MVP)
- Steep learning curve for operators
- Added complexity (manifests, services, ingress)

**Rejected**: Too heavy for MVP; defer to post-pilot scaling phase.

#### Option C: Bare Metal + systemd
**Description**: Install Python directly on host, use systemd service

**Pros**:
- No Docker dependency
- Direct resource access

**Cons**:
- Environment reproducibility issues (Python versions, dependency conflicts)
- Manual setup (not single-command)
- Harder to migrate/backup

**Rejected**: Prefer containerized approach for reproducibility.

### Decision
**Use Docker + Docker Compose** for MVP deployment.

**Validation Criteria**:
- Operator can deploy from scratch with `docker compose up -d` in <5 minutes
- Service survives host reboot (restart policy)
- Data persists across container updates (volume mounts)

---

## Summary Table

| Decision | Selected Option | Key Trade-off | Validation Metric |
|----------|----------------|---------------|------------------|
| Google Trends Access | pytrends | Unofficial API vs. stability | ≥99% fetch success rate |
| Stitching Algorithm | Trimmed Mean | Simplicity vs. statistical efficiency | <20% jumps on stable days |
| Sparse-Day Policy | 3-Step Fallback | Honesty vs. completeness | ≥90% true_daily quality |
| Scheduling | APScheduler | Self-contained vs. cron familiarity | 99% runs within 10min of target |
| Storage | SQLite WAL | Simplicity vs. scalability | <100ms query latency |
| Health Endpoint | Flask | Lightweight vs. feature-richness | <100ms response time |
| Logging | JSON | Parsability vs. human-readability | Operators can filter by batch_id |
| Configuration | TOML | Type-safety vs. flexibility | All params documented inline |
| Deployment | Docker Compose | Reproducibility vs. bare-metal performance | <5min setup from scratch |

---

**Status**: ✅ Complete and aligned with Googili constitution v1.1.0

**Last Updated**: 2025-11-04
**Next Review**: On completion of 6-month pilot (constitution quarterly review)
