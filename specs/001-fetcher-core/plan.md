# Implementation Plan: Fetcher Core - Google Trends RSV Data Ingestion

**Branch**: `001-fetcher-core` | **Date**: 2025-11-04 | **Updated**: 2025-11-07 (Simplified) | **Spec**: [spec.md](./spec.md)
**Input**: Simplified feature specification with daily 'today 1-m' ingestion + stitching

## Summary

Build a streamlined Fetcher core that reliably ingests Google Trends RSV for ~10 Thai ILI-related keywords (Thailand-wide), produces a stitched, provenance-rich daily series via overlap-based scaling, and emits ingestion events—fully aligned with the Googili constitution v1.1.0.

**Key Capabilities**: Daily ingestion using pytrends 'today 1-m' timeframe (~30 days rolling window); one-keyword-per-request to respect API limits; overlap-based stitching for continuous time series; idempotent UPSERT for safe re-runs; complete provenance tracking; config-as-code.

**Strict Boundaries (Constitution Principle II)**: Fetcher writes raw RSV + stitched RSV + batch events to SQLite; no analysis, no dashboards, no cross-core function calls. Communication strictly via database tables.

**Simplified from Original Plan** (per GitHub issue #4):
- ❌ **Removed**: 90-day historical backfill, gap recovery (14-day rolling backfill), sparse-day resampling, weekly promotion, APScheduler daemon mode
- ✅ **Kept**: Daily ingestion with 'today 1-m', overlap-based stitching, provenance tracking, rate limiting
- ✅ **Added**: One-keyword-per-request loop (fixes HTTP 400), explicit jitter between requests (3-5 seconds)

## Technical Context

**Language/Version**: Python 3.12

**Primary Dependencies**:
- `pytrends` (Google Trends unofficial API client) - native 'today 1-m' timeframe
- `scipy` (trimmed mean for robust stitching algorithm)
- `sqlite3` (built-in, with WAL mode)
- NO APScheduler (removed - external cron used instead)
- NO Flask/FastAPI (health endpoint deferred to future phase)

**Storage**: SQLite 3 with WAL mode; single file for MVP (raw_trenddata, events_raw_rsv_ingested, config_keywords tables)

**Testing**: pytest with:
- Unit tests (stitching, overlap detection, UPSERT idempotence)
- Integration tests (full ingestion with stitching workflow)
- Contract tests (event emission, database schema compliance)
- NO golden-file tests yet (planned for Phase 2 stitching implementation)

**Target Platform**: macOS/Linux (containerization deferred); Asia/Bangkok timezone

**Project Type**: Single backend service (CLI only - simplified main.py)

**Performance Goals**:
- Daily fetch+stitch for 10 keywords < 2 minutes (with 3-5 second jitter between keywords = ~60 seconds jitter time)
- UPSERT operation idempotent - safe to re-run without duplicates
- Stitching computation < 1 second per keyword (simple trimmed mean on overlap region)

**Constraints**:
- **Timeliness**: Manual or cron-triggered daily ingestion (no built-in scheduler in MVP)
- **Zero duplicates**: unique (keyword, date) PRIMARY KEY constraint enforced
- **Append-only**: UPSERT semantics allow re-ingestion without data loss
- **API Limits**: ONE keyword per request (max 5 keywords per pytrends request, but we use 1 for safety)

**Scale/Scope**:
- 10 Thai keywords (Thailand TH country-wide, changed from TH-50 Chiang Mai)
- ~30 days of rolling data per ingestion (actual: 32-33 days from 'today 1-m')
- Overlapping windows provide 29-30 days of overlap for stitching
- Modest hardware (2 CPU, 4GB RAM sufficient)
- Single-server deployment

## Constitution Check

*GATE: Must pass before implementation. All checks reflect SIMPLIFIED scope.*

### Principle I: Adjunct Signal, Not Diagnostic ✅
- Fetcher emits raw RSV + stitched RSV with explicit batch event metadata
- No interpretation, no thresholds, no analysis—strictly data ingestion + stitching
- All records have `granularity='daily'` and `quality='true'` (no weekly promotion in MVP)

### Principle II: Separation of Concerns (Three Cores) ✅
- **Strict boundary**: Fetcher writes; Analyser/Visualiser read (future)
- Communication via database tables (`events_raw_rsv_ingested`, `raw_trenddata`) only
- No direct function calls; each core runs independently
- **Decision**: Shared SQLite file (`/data/raw/rsv_trends.db`) with centralized data directory structure

### Principle III: Test-Driven Development (NON-NEGOTIABLE) ✅
- TDD mandatory for all core logic:
  - Unit: stitching algorithm (trimmed mean), overlap window calculation, UPSERT idempotence
  - Integration: full ingestion workflow with stitching
  - Contract: batch events schema compliance
- **Current Status**: Tests exist but need updating for simplified `ingest()` method (see Phase 4)
- Red-Green-Refactor cycle to be enforced for stitching implementation

### Principle IV: Data Governance & Provenance ✅
- Every batch event records: batch_id, keywords, window, row counts, timestamps (ICT), stitching metadata
- Every RSV record includes: raw value (rsv_raw), stitched value (rsv_stitched), source window, batch_id, fetch timestamp
- Scaling factors stored in batch event notes for audit trail (e.g., "Stitching keyword='ไข้': factor=1.18, overlap=29 days")
- No personal data; only aggregated RSV values

### Principle V: Fail-Safe & Availability ✅
- Database-first approach: last good data always queryable even if Fetcher offline
- Batch events record status (success/degraded/fail) for monitoring
- **Health endpoint deferred** (not in MVP - operators use batch event queries instead)

### Principle VI: Clarity Over Cleverness ✅
- Simple overlap-based stitching using **trimmed mean with 20% trim** (literature-supported, explainable)
- No complex models or interpolation
- Plain-language batch event notes (e.g., "overlap=29 days, factor=1.18", "warning: overlap <3 days")
- One-keyword-per-request loop is explicit and understandable (vs. complex batching logic)

### Principle VII: Configuration-as-Code (Single File) ✅
- `config/googili.toml` specifies: keywords, province (TH), language (en-US), jitter_seconds, stitching params (min_overlap_days, trim_percent)
- Version-controlled; no in-app config UI
- System logs effective parameters at startup

### Principle VIII: Observability & Data Health ✅
- Structured JSON logs per batch (keywords, rows_written, rows_updated, duration, stitching metadata)
- Batch events table queryable for monitoring ("What was last successful fetch?", "Any failed batches?")
- **Health endpoint deferred to future phase** - operators query database directly for now

### Principle IX: Equity & Ethical Communication ✅
- Batch event notes emphasize data limitations (e.g., "RSV is media-sensitive, not disease count")
- Documentation acknowledges digital divide (search data != disease surveillance)
- No stigmatizing language; transparent about stitching adjustments

### Principle X: User Experience & Accessibility ⚠️ NOT APPLICABLE (Fetcher Core)
- Fetcher is a backend service with CLI only
- Visualiser core (future, separate feature) handles UI/accessibility requirements

**GATE RESULT**: ✅ PASS - All applicable principles satisfied with simplified scope.

## Project Structure

### Documentation (this feature)

```text
specs/001-fetcher-core/
├── plan.md              # This file (updated for simplified scope)
├── spec.md              # Feature spec (updated to remove backfill/resampling)
├── research.md          # Technology decisions (pytrends, stitching algorithms, WAL mode)
├── data-model.md        # SQLite schema (raw_trenddata with rsv_stitched column)
├── quickstart.md        # Operator runbook (setup, manual run, cron config)
└── tasks.md             # Task breakdown (updated to reflect simplified scope + stitching)
```

### Source Code (ACTUAL current structure)

```text
fetcher/
├── src/
│   ├── models/
│   │   ├── rsv_record.py       # ✅ RSV Record domain model
│   │   ├── batch_event.py      # ✅ Batch Event (supports 'ingestion' type)
│   │   └── keyword_config.py   # ✅ Keyword Configuration model
│   ├── services/
│   │   ├── trends_fetcher.py   # ✅ pytrends integration (fetch_daily_rsv with 'today 1-m')
│   │   ├── stitcher.py         # ❌ NOT IMPLEMENTED (Phase 2 - next step)
│   │   ├── ingestion.py        # ✅ SIMPLIFIED - single ingest() method, one keyword per request
│   │   └── scheduler.py        # ⚠️ EXISTS but unused (no daemon mode in simplified main.py)
│   ├── lib/
│   │   ├── db.py               # ✅ SQLite connection, WAL mode, init_database()
│   │   ├── db_operations.py    # ✅ UPSERT helpers, batch event ops
│   │   ├── config.py           # ✅ TOML config loader (FetcherConfig)
│   │   ├── logging_utils.py    # ✅ Structured JSON logging
│   │   ├── timezone_utils.py   # ✅ ICT timezone utilities
│   │   └── exceptions.py       # ✅ Custom exceptions (StitchingException exists but unused)
│   └── __init__.py
├── tests/
│   ├── contract/
│   │   ├── test_batch_event_schema.py      # ✅ Contract tests
│   │   └── test_rsv_record_schema.py       # ✅ Schema compliance
│   ├── integration/
│   │   ├── test_daily_ingestion.py         # ⚠️ BROKEN - calls deleted ingest_daily()
│   │   ├── test_end_to_end.py              # ⚠️ BROKEN - calls deleted ingest_daily()
│   │   └── test_cli_integration.py         # ⚠️ Needs update for simplified CLI
│   ├── unit/
│   │   ├── test_stitcher.py                # ❌ NOT IMPLEMENTED (Phase 2)
│   │   ├── test_trends_fetcher.py          # ✅ Tests exist
│   │   ├── test_db_operations.py           # ✅ UPSERT tests
│   │   ├── test_config.py                  # ⚠️ References deleted backfill properties
│   │   ├── test_cli.py                     # ⚠️ Tests deleted run_manual(), run_daily()
│   │   └── test_scheduler_behavioral.py    # ⚠️ Mocks deleted ingest_daily()
│   └── golden/
│       └── (empty - planned for stitching scenarios)
├── config/
│   └── googili.toml             # ✅ Updated config (province=TH, jitter_seconds, [stitching] section)
├── main.py                      # ✅ SIMPLIFIED CLI - single run_ingestion() function
├── schema.sql                   # ✅ Schema with rsv_stitched column, 'ingestion' batch_type
├── requirements.txt             # ✅ pytrends, scipy, pytest
└── README.md
```

**Key Changes from Original Plan**:
- ❌ **Deleted Files**: `services/backfill.py`, `services/resampler.py`, `services/archiver.py`
- ❌ **Deleted Tests**: `test_initial_backfill.py`, `test_ingestion_behavior.py` (backfill tests)
- ⚠️ **Needs Implementation**: `services/stitcher.py` (Phase 2)
- ⚠️ **Needs Fixes**: Multiple test files reference deleted `ingest_daily()` method (Phase 4)

## Architecture Decisions

### 1. Google Trends Access: pytrends with 'today 1-m' Timeframe

**Decision**: Use `pytrends` library with native 'today 1-m' timeframe format, fetch ONE keyword per request

**Rationale**:
- Pytrends supports relative timeframes like 'today 1-m' (past ~30 days) natively - no date calculation needed
- **HTTP 400 Fix**: Sending 10 keywords at once exceeded API limit (max 5 keywords per request) - loop through keywords individually
- ONE keyword per request is conservative (well under 5-keyword limit), prevents future API errors
- 3-5 second jitter between requests prevents rate limiting

**Alternatives Considered** (per GitHub issue #4):
- ❌ Batch keywords in groups of 5 - rejected (complex logic, still risky)
- ❌ Calculate explicit date ranges - rejected (pytrends 'today 1-m' is simpler, more reliable)
- ❌ Use pytrends retry logic - rejected (pytrends does NOT auto-retry HTTP 429)

**Implementation** (CURRENT - ingestion.py lines 130-149):
```python
# ONE keyword per request to respect pytrends API limits
for keyword in keywords:
    logger.info(f"Fetching RSV for keyword: {keyword}")

    keyword_records = self.trends_fetcher.fetch_daily_rsv(
        keywords=[keyword],  # ONE keyword per request
        batch_id=batch_event.batch_id,
        timeframe='today 1-m'  # Native pytrends format
    )
    all_records.extend(keyword_records)

    # Apply jitter between requests (except after last keyword)
    if keyword != keywords[-1]:
        self.trends_fetcher._apply_jitter()  # 3-5 second sleep
```

**Rate Limiting Handling**:
- **Preventive jitter**: Random 3-5 second sleep between keyword requests
- **Reactive retry**: Exponential backoff on HTTP 429 (60s, 300s, 1500s base, multiplier 5.0, max 1800s)
- **Configuration**: Retry behavior in `[rate_limiting]` section of googili.toml
- **Batch status**: Mark as 'fail' (not 'degraded') on HTTP 429 - operators must manually re-run after waiting

### 2. Time-Series Stitching: Overlap-Based Scaling with Trimmed Mean

**Decision**: Compute scaling factor from overlap region using **trimmed mean with 20% trim** from each tail

**Rationale**:
- **Problem**: Each day's 'today 1-m' fetch returns INDEPENDENT 0-100 scale (normalized to that window's peak)
- **Example**: Oct 9 has RSV=45 on Day 1, RSV=38 on Day 2 (same date, different scales) - creates artificial jumps
- **Solution**: Use 29-day overlap region to compute robust scaling factor, apply to new (non-overlapping) data
- Trimmed mean down-weights outliers (single-day spikes) without complex statistics
- Simple, explainable to non-technical analysts
- Preserves zero values (if `new_trimmed == 0`, scaling_factor = 1.0)
- Literature-supported (referenced in research.md)

**Alternatives Considered**:
- Median (too aggressive for small overlaps)
- Mean (vulnerable to outliers)
- Regression-based (overfitting risk, not explainable)

**Implementation Status**: ❌ NOT YET IMPLEMENTED
- Schema ready: `rsv_stitched REAL` column exists in raw_trenddata table
- Config ready: `[stitching]` section with min_overlap_days=1, trim_percent=20
- Exception ready: `StitchingException` defined in exceptions.py
- **Phase 2 Next Steps**:
  1. Create `services/stitcher.py` with StitcherService class
  2. Implement `find_overlap()`, `compute_scaling_factor()`, `apply_stitching()` methods
  3. Integrate into IngestionService.ingest() after fetch, before persist

**Algorithm Specification** (from research.md):
```python
from scipy.stats import trim_mean

def compute_scaling_factor(old_overlap: List[float], new_overlap: List[float]) -> float:
    """
    Compute scaling factor using trimmed mean (20% trim from each tail).

    Args:
        old_overlap: RSV values from existing data for overlap dates
        new_overlap: RSV values from new fetch for same overlap dates

    Returns:
        scaling_factor: old_trimmed / new_trimmed
    """
    if len(old_overlap) < 1:  # min_overlap_days = 1
        raise StitchingException("Insufficient overlap")

    old_trimmed = trim_mean(old_overlap, proportiontocut=0.2)  # Drop top/bottom 20%
    new_trimmed = trim_mean(new_overlap, proportiontocut=0.2)

    if new_trimmed == 0:
        return 1.0  # Preserve zeros, no manufactured signal

    return old_trimmed / new_trimmed
```

**Workflow** (planned integration into ingestion.py):
1. Fetch keyword data using 'today 1-m' (e.g., Oct 10 - Nov 8)
2. Query database for existing records for same keyword in date range
3. **If overlap exists** (e.g., Oct 10 - Nov 7 already in DB):
   - Extract overlap_dates (Oct 10 - Nov 7 = 29 days)
   - old_overlap = [rsv_stitched from DB for Oct 10-Nov 7]
   - new_overlap = [rsv_raw from new fetch for Oct 10-Nov 7]
   - scaling_factor = compute_scaling_factor(old_overlap, new_overlap)
   - Apply to NEW data only (Nov 8): rsv_stitched = rsv_raw * scaling_factor
   - Store scaling_factor in batch_event.notes
4. **If no overlap** (first fetch for keyword):
   - rsv_stitched = rsv_raw (no scaling needed)
5. Persist records with both rsv_raw and rsv_stitched

**Quality Flags**:
- Warn if overlap < 3 days (log in batch event notes)
- Minimum 1 day overlap required (configurable: `min_overlap_days`)
- Exclude coarse records from overlap query: `WHERE quality='true'` (prevents normalization drift)

### 3. Removed: Sparse-Day Resampling

**Decision**: ❌ REMOVED from simplified scope (per GitHub issue #4)

**Original Plan**: 3-step fallback (re-fetch → weekly promotion → below_detection)

**Current Reality**: All records have `granularity='daily'` and `quality='true'`. No weekly promotion, no resampling logic.

**Rationale for Removal**:
- 'today 1-m' consistently returns daily data for keywords with any search volume
- Weekly promotion adds complexity without clear value for MVP
- Operators can manually handle edge cases (below-detection keywords)

**Future Consideration**: If daily data becomes sparse, resampling policy can be re-added in future phase

### 4. Removed: APScheduler Daemon Mode

**Decision**: ❌ REMOVED in-container scheduling (per GitHub issue #4 simplification)

**Original Plan**: APScheduler with ±3-5 min jitter, runs at 07:30 ICT inside Docker container

**Current Reality**: Simplified `main.py` with single `run_ingestion()` function. Operators use:
- **Manual runs**: `cd fetcher && python main.py`
- **External cron**: `30 7 * * * cd /path/to/googili/fetcher && python main.py` (crontab on host)

**Rationale for Removal**:
- Simpler deployment (no daemon process management)
- Easier debugging (single execution, clear logs)
- MVP-appropriate (manual or cron sufficient for pilot)

**Implementation**: main.py lines 91-135 - single `run_ingestion(db_path, schema_path)` function

### 5. Storage: SQLite with WAL Mode (UNCHANGED)

**Decision**: Single SQLite file (`/data/raw/rsv_trends.db`) with Write-Ahead Logging (WAL) mode

**Rationale**: Same as original plan - simple, file-based, no separate DB server, concurrent reads while Fetcher writes

**Current Implementation**: ✅ WORKING
- Database at `/data/raw/rsv_trends.db` (centralized data directory, shared across modules)
- WAL mode enabled in `lib/db.py:init_database()`
- PRIMARY KEY (keyword, date) enforces uniqueness
- UPSERT on conflict: `INSERT ON CONFLICT(keyword, date) DO UPDATE`

### 6. Removed: Health Endpoint

**Decision**: ❌ DEFERRED to future phase (not in simplified MVP)

**Original Plan**: Flask app serving `/healthz` on port 8080

**Current Reality**: No HTTP server. Operators query database directly for monitoring:
```sql
-- Check last successful batch
SELECT batch_id, status, finished_at_ict, rows_written
FROM events_raw_rsv_ingested
ORDER BY started_at_ict DESC LIMIT 1;

-- Check data freshness
SELECT keyword, MAX(date) as latest_date
FROM raw_trenddata
GROUP BY keyword;
```

**Future Consideration**: Health endpoint can be added when operational monitoring requirements are clarified

## Data Flow

**Simplified Daily Ingestion Workflow** (current implementation):

```
1. User runs: python main.py
2. Load config from googili.toml (keywords, province, stitching params)
3. Create batch_event (batch_id, status='running', keywords, window)
4. FOR EACH keyword (ONE at a time):
   4a. Fetch RSV data using 'today 1-m' (pytrends)
   4b. [FUTURE] Detect overlap with existing data in DB
   4c. [FUTURE] Compute scaling factor (trimmed mean)
   4d. [FUTURE] Apply stitching to new data
   4e. [CURRENT] Store records (rsv_raw, rsv_stitched=NULL for now)
   4f. Apply 3-5 second jitter (unless last keyword)
5. UPSERT all records to database (idempotent)
6. Update batch_event (status='success', rows_written, rows_updated, duration, notes)
7. Log completion (structured JSON)
```

**With Stitching** (Phase 2 implementation):

```
4b. Query DB: SELECT * FROM raw_trenddata WHERE keyword=? AND date BETWEEN ? AND ? AND quality='true'
4c. IF overlap_records found:
    - Extract old_overlap = [rsv_stitched from DB]
    - Extract new_overlap = [rsv_raw from new fetch for overlap dates]
    - scaling_factor = trimmed_mean(old_overlap, 0.2) / trimmed_mean(new_overlap, 0.2)
    - Apply to NEW data: rsv_stitched = rsv_raw * scaling_factor
    - Store scaling_factor in batch_event.notes
   ELSE (first fetch):
    - rsv_stitched = rsv_raw (no scaling)
```

## Success Metrics (Updated for Simplified Scope)

From spec.md, updated to reflect current implementation:

- **SC-001**: Daily RSV data retrieved and stored successfully on 99% of runs
- **SC-002**: Zero duplicate (keyword, date) records (enforced by PRIMARY KEY + UPSERT) ✅
- **SC-003**: Daily ingestion completes <10 min for 10 keywords (with jitter) ✅
- **SC-004**: Stitched series shows <20% jumps on stable days (to be validated after Phase 2 stitching)
- **SC-006**: 100% batch events include complete provenance (batch_id, timestamps, rows, notes) ✅
- **SC-007**: Operators can trace any record to batch event via batch_id ✅
- **SC-008**: ≥99% fetch success rate (operational reliability)
- **SC-009**: Stitching degradation warnings (overlap <3 days) logged in batch notes (after Phase 2)
- **SC-010**: HTTP 429 errors handled with exponential backoff ✅

**Removed Metrics** (no longer applicable):
- ~~SC-003: 90-day backfill <15 min~~ (no backfill in simplified scope)
- ~~SC-005: 14-day recovery backfill~~ (no gap recovery)

## Risks & Mitigations (Updated)

**Risk**: Google Trends HTTP 429 rate limiting
- **Mitigation**: ✅ 3-5 second jitter between keywords; exponential backoff retry (60s, 300s, 1500s); operators re-run manually if needed

**Risk**: HTTP 400 from exceeding keyword limit
- **Mitigation**: ✅ FIXED - one keyword per request (issue #4)

**Risk**: Stitching algorithm produces incorrect scaling factors
- **Mitigation**: [Phase 2] Unit tests with known overlap scenarios; batch event notes store scaling factors for audit; operators can inspect rsv_raw vs. rsv_stitched

**Risk**: Overlap < 3 days reduces stitching confidence
- **Mitigation**: [Phase 2] Warn in batch notes; still compute scaling factor (min 1 day); operators alerted to degraded quality

**Risk**: Database grows large (>100k records)
- **Mitigation**: SQLite handles 100k+ rows efficiently; monthly exports can be added later for archival

**Risk**: Timezone confusion (ICT vs. UTC)
- **Mitigation**: ✅ All timestamps explicitly Asia/Bangkok in schema; timezone_utils.py enforces ICT; documented in code

## Phase Summary

### Phase 0: Research ✅ COMPLETE
- Pytrends library validated
- Stitching algorithm researched (trimmed mean)
- Database schema designed with rsv_stitched column

### Phase 1: Design ✅ COMPLETE
- spec.md updated (removed backfill/resampling, kept stitching)
- plan.md updated (this file)
- tasks.md needs update (Phase 1 next step)

### Phase 2: Stitching Implementation [NEXT]
- TDD: Write unit tests for StitcherService first
- Implement StitcherService (find_overlap, compute_scaling_factor, apply_stitching)
- Integrate into IngestionService
- Validate stitching with integration tests

### Phase 3: Test Fixes [AFTER PHASE 2]
- Fix 70+ broken test calls to deleted ingest_daily() method
- Rewrite test_cli.py for simplified CLI
- Update test_config.py (remove backfill, keep stitching)
- Create test_ingestion_simplified.py with new tests

### Phase 4: Configuration & Schema Fixes
- Fix schema province constraint (support TH and TH-50)
- Add rate_limiting to root config/googili.toml
- Update schema comments

### Phase 5: Verification
- Run full test suite (achieve 100% pass rate)
- Verify workflow: Day 1 ingestion (no stitching), Day 2 ingestion (with stitching)
- Document stitching validation results

## Next Steps

**IMMEDIATE** (this session):
1. ✅ Update spec.md (completed)
2. ✅ Update plan.md (this file, completed)
3. 🔄 Update tasks.md - mark Phase 5 (stitching) as current work, remove Phase 4/6/7 (backfill/recovery/resampling)

**PHASE 2** (stitching implementation):
4. Write unit tests for StitcherService (TDD - tests FIRST)
5. Implement StitcherService
6. Integrate stitching into IngestionService
7. Write integration tests for full stitching workflow

**PHASE 3** (test fixes):
8. Fix test_daily_ingestion.py (49 calls to ingest_daily)
9. Fix test_end_to_end.py, test_scheduler_behavioral.py, test_cli.py
10. Update test_config.py
11. Create test_ingestion_simplified.py

**PHASE 4** (config/schema):
12. Fix schema province constraint
13. Add rate_limiting to root config

**PHASE 5** (verification):
14. Run full test suite
15. Verify stitching workflow
16. Document results

**Operator Action Required**: None for now - spec and plan updates are documentation changes only. Implementation work begins in Phase 2.
