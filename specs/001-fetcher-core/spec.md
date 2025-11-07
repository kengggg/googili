# Feature Specification: Fetcher Core - Google Trends RSV Data Ingestion

**Feature Branch**: `001-fetcher-core`
**Created**: 2025-11-04
**Updated**: 2025-11-07 (Simplified per GitHub issue #4)
**Status**: Active Development
**Input**: Simplified ingestion with daily 'today 1-m' fetch + stitching for continuous time series

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Daily RSV Data with Stitching (Priority: P1)

SAT operators and analysts need reliable, up-to-date Google Trends search volume data for ~10 Thai ILI-related keywords in Thailand to support their weekly surveillance huddles and early warning assessments. The data must form a continuous, comparable time series despite Google's independent normalization of each fetch window.

**Why this priority**: This is the foundational capability that enables all downstream analysis and alerting. Daily ingestion provides fresh data (~30 days rolling window), while stitching ensures the time series remains stable and interpretable across days.

**Independent Test**: Can be fully tested by running daily ingestion for multiple consecutive days, verifying that RSV data appears in the database with both `rsv_raw` and `rsv_stitched` values, and confirming that stitched values maintain level consistency (no normalization jumps) across overlapping windows.

**Acceptance Scenarios**:

1. **Given** the system is configured with 10 Thai keywords for Thailand (TH), **When** the daily ingestion runs, **Then** RSV data for all 10 keywords is retrieved using 'today 1-m' timeframe (~30 days), processed ONE keyword per request with 3-5 second jitter to respect API limits, and stored with complete provenance metadata within 10 minutes.

2. **Given** this is the first ingestion run (no existing data), **When** the ingestion completes, **Then** all records are stored with `rsv_stitched = rsv_raw` (no stitching needed), batch event is created with type='ingestion', and Data Health widget shows "last successful fetch" timestamp.

3. **Given** previous day's data exists, **When** today's ingestion runs with overlapping dates (e.g., Oct 9-Nov 7 yesterday, Oct 10-Nov 8 today), **Then** the system detects the 29-day overlap, computes a robust scaling factor using trimmed mean (20% trim), applies stitching to new data (Nov 8), and logs the scaling factor in batch event notes for audit trail.

4. **Given** analysts examine the stitched time series, **When** they review consecutive days with stable search behavior, **Then** they observe `rsv_stitched` values that do not show level jumps attributable to normalization differences (validated: no jumps >20% on stable days).

5. **Given** an overlap contains outlier days (single-day spikes), **When** the scaling factor is computed, **Then** the trimmed mean algorithm down-weights the outliers (drops highest/lowest 20%) to prevent them from distorting the stitching.

---

### Edge Cases

- **What happens when Google Trends returns all zeros for a keyword across multiple days?**
  The system stores those days with granularity=daily, quality=true, and `rsv_raw=0`, `rsv_stitched=0.0`. Stitching preserves zeros (no manufactured signal). If the zeros span ≥3 consecutive days, they trigger a Data Health alert visible to operators.

- **What happens when the overlap window between consecutive fetches is less than 3 days?**
  The system logs a stitching degradation warning in the batch event notes (e.g., "Stitching: keyword='ไข้', overlap=2 days, warning: <3 days"). The scaling factor is still computed using available overlap (minimum 1 day per config), but operators are alerted to reduced confidence.

- **What happens when an ingestion run fails due to HTTP 429 rate limiting?**
  The system marks the batch event as 'fail' (not 'degraded'), logs the error with structured metadata, and implements exponential backoff retry (3 attempts: 60s, 300s, 1500s). Operators can manually re-run ingestion after waiting.

- **What happens when a keyword is removed from the configuration mid-deployment?**
  Historical data for that keyword remains in the database (append-only integrity), but future ingestions skip it. Stitching continues for remaining active keywords.

- **What happens when pytrends API sends 10 keywords in one request (exceeding limit)?**
  The system loops through keywords and fetches ONE keyword per request (issue #4 fix), applying 3-5 second jitter between requests. This prevents HTTP 400 errors from exceeding the 5-keyword API limit.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST fetch daily Google Trends RSV (0–100) for all configured Thai keywords scoped to Thailand (TH) using pytrends native 'today 1-m' timeframe (approximately 30 days of daily data per request).

- **FR-002**: System MUST fetch ONE keyword per request (not batch) to respect Google Trends API limits (max 5 keywords per request), applying 3-5 second jitter between requests to prevent rate limiting.

- **FR-003**: System MUST detect overlapping date ranges between consecutive ingestion runs by querying existing records in the database for each keyword.

- **FR-004**: System MUST compute a robust scaling factor for stitching using **trimmed mean with 20% trim** from each tail of the overlap region RSV values, down-weighting outliers and single-day spikes.

- **FR-005**: System MUST apply the computed scaling factor to new (non-overlapping) data points, storing both `rsv_raw` (from Google) and `rsv_stitched` (scaled value) for every record.

- **FR-006**: System MUST preserve zero values as zero (no manufactured signal) during stitching: if `new_trimmed == 0`, scaling_factor defaults to 1.0.

- **FR-007**: System MUST warn operators when overlap between consecutive fetches is less than 3 days (via batch event notes), while still computing scaling factor from available overlap (minimum 1 day per configuration).

- **FR-008**: System MUST store scaling factors in batch event notes for audit trail (e.g., "Stitching keyword='ไข้': factor=1.18, overlap=29 days").

- **FR-009**: System MUST ensure no duplicate (keyword, date) pairs exist in published data by using UPSERT semantics (INSERT ON CONFLICT UPDATE), enforcing PRIMARY KEY constraint on (keyword, date).

- **FR-010**: System MUST store complete provenance metadata for every record: `keyword`, `date`, `rsv_raw`, `rsv_stitched`, `source_window_start`, `fetched_at_ict`, `batch_id`, `granularity`, `quality`.

- **FR-011**: System MUST emit an "ingestion complete" event after each batch, recording batch_id, status (success/degraded/fail), start/end timestamps (Asia/Bangkok), row counts (inserted/updated), and notes (stitching metadata, warnings).

- **FR-012**: System MUST exclude coarse (weekly-derived) records from future stitching factor computations by filtering `WHERE quality='true'` when querying overlap region (prevents normalization drift).

- **FR-013**: System MUST handle HTTP 429 rate limiting errors with exponential backoff retry strategy (3 attempts: 60s, 300s, 1500s base, multiplier 5.0, max 1800s), respecting Retry-After header if present.

- **FR-014**: System MUST read all operational parameters (keywords, geography, stitching config, jitter, rate limiting) from a single TOML configuration file (`googili.toml`) with no in-app UI editing.

- **FR-015**: System MUST use idempotent UPSERT semantics for data persistence, making daily ingestion safe to re-run without creating duplicates or data loss.

- **FR-016**: System MUST log all operations with structured JSON logging, including batch_id, keyword, status, errors, and performance metrics for observability.

- **FR-017**: System MUST support manual inspection of raw vs. stitched values by storing both `rsv_raw` (integer 0-100) and `rsv_stitched` (real, scaled) in separate columns.

### Key Entities

- **RSV Record**: Represents a single (keyword, date) observation with:
  - `keyword` (TEXT): Thai ILI symptom term (e.g., ไข้, ไอ, เจ็บคอ)
  - `date` (DATE): Observation date
  - `rsv_raw` (INTEGER 0-100): Raw value from Google Trends (normalized to request window)
  - `rsv_stitched` (REAL, nullable): Scaled value after stitching (comparable across days)
  - `source_window_start` (DATE): First date in the fetch window (for provenance)
  - `fetched_at_ict` (TIMESTAMP): When this record was retrieved (Asia/Bangkok timezone)
  - `batch_id` (TEXT): Links to batch event for complete lineage
  - `granularity` (TEXT): 'daily' or 'weekly' (currently always 'daily')
  - `quality` (TEXT): 'true' (reliable) or 'coarse' (derived, excluded from future stitching)
  - PRIMARY KEY: (keyword, date)

- **Batch Event**: Represents a single ingestion run with:
  - `batch_id` (TEXT): Unique identifier (format: batch_YYYYMMDD_HHMMSS)
  - `batch_type` (TEXT): 'ingestion' (standard daily run)
  - `requested_keywords` (JSON array): List of keywords fetched
  - `requested_window` (TEXT): Approximate date range (e.g., "2025-10-08 to 2025-11-07")
  - `started_at_ict` (TIMESTAMP): Batch start time
  - `finished_at_ict` (TIMESTAMP): Batch completion time
  - `status` (TEXT): 'running', 'success', 'degraded', 'fail'
  - `rows_written` (INT): Count of records inserted
  - `rows_updated` (INT): Count of records updated (re-ingestion)
  - `notes` (TEXT): Audit notes including stitching metadata (e.g., scaling factors, warnings)
  - `error_message` (TEXT): Error details if status='fail'

- **Keyword Configuration**: Represents a Thai symptom keyword with:
  - `term` (TEXT): The keyword (e.g., ไข้, ไอ)
  - `province_code` (TEXT): Geographic scope ('TH' for Thailand-wide)
  - `is_active` (BOOLEAN): Whether to include in current ingestions
  - Managed in `googili.toml` under `[keywords]` section

- **Stitching Configuration**: Parameters for overlap-based stitching:
  - `min_overlap_days` (INT): Minimum required overlap (default: 1, warn if <3)
  - `trim_percent` (INT): Percentage to trim from each tail (default: 20, range 0-50)
  - Managed in `googili.toml` under `[stitching]` section

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Daily RSV data for all configured keywords is retrieved and stored successfully on 99% of scheduled runs during pilot.

- **SC-002**: Zero duplicate (keyword, date) records exist in the published time series across all ingestion runs (enforced by PRIMARY KEY constraint + UPSERT).

- **SC-003**: Daily ingestion completes within 10 minutes for 10 keywords, fetching ~30 days per keyword with one-keyword-per-request and 3-5 second jitter (approximately 60 seconds of jitter time + fetch time).

- **SC-004**: Stitched time series shows no level jumps exceeding 20% on consecutive days with stable search behavior (validated against test scenarios with controlled overlaps and known scaling factors).

- **SC-005**: Stitching algorithm correctly down-weights outliers: when overlap contains single-day spikes, the trimmed mean (20% trim) produces scaling factors that differ from simple mean by >10% (demonstrating outlier robustness).

- **SC-006**: 100% of batch events include complete provenance metadata (batch_id, timestamps, requested window, row counts, status, stitching notes) for audit trail.

- **SC-007**: Operators can trace any RSV record back to its originating batch event via `batch_id`, viewing the exact fetch timestamp, window parameters, and stitching metadata used.

- **SC-008**: Field pilot demonstrates ≥99% fetch success rate per week with clear visibility of any failed batches via structured logs and batch event status.

- **SC-009**: Stitching degradation warnings (overlap <3 days) are logged in batch event notes and visible to operators for quality assessment.

- **SC-010**: HTTP 429 rate limiting errors are handled gracefully with exponential backoff, preventing cascade failures and enabling eventual success after retries.

### Assumptions

- Google Trends API/interface remains stable and accessible during pilot (no major algorithmic or access changes).
- Network connectivity between the system and Google Trends is reliable with occasional brief outages (<1 hour).
- ~10 Thai keywords are sufficient for initial Thailand ILI surveillance; keyword list refinement will occur post-pilot.
- The 'today 1-m' timeframe consistently returns approximately 30 days of daily data (validated: typically 32-33 days in practice).
- Overlapping windows of 29-30 days between consecutive daily runs provide sufficient overlap for robust stitching (far exceeding minimum 1-day threshold).
- Operators have access to structured logs (JSON) and batch event queries for monitoring and troubleshooting.
- The system runs on modest hardware with sufficient storage for 90+ days of daily records for 10 keywords (approximately 28,000 records at steady state).
- All timestamps use Asia/Bangkok (ICT) timezone for consistency with local public health workflows.
- Database uses SQLite with WAL mode for append-only writes and concurrent read access.
- Configuration changes (keyword additions/removals) require system restart to take effect.

### Dependencies

- **pytrends library**: Python wrapper for Google Trends API with 'today 1-m' timeframe support.
- **scipy library**: Provides `trim_mean` function for robust stitching algorithm.
- **Database Layer**: SQLite with WAL mode, schema with rsv_stitched column and stitching-ready structure.
- **Configuration System**: `googili.toml` file exists and is version-controlled with `[stitching]` section.
- **Scheduler** (future): Cron or equivalent scheduling mechanism to trigger daily ingestion at 07:30 ICT (not yet implemented in main.py).
- **Google Trends Access**: pytrends library provides scraping interface compliant with Google's terms of use (public data).

### Out of Scope (Removed Features)

- **90-Day Historical Backfill** (User Story 2): Removed per GitHub issue #4. The 'today 1-m' approach provides 30 days of rolling history, which is sufficient for operational surveillance. Historical context beyond 30 days is not required for MVP.

- **Gap Recovery After Outages** (User Story 4): Removed per GitHub issue #4. Operators can manually re-run ingestion if needed. Automatic gap detection and 14-day rolling backfill are not implemented.

- **Data Quality Granularity Badges** (User Story 5): Weekly promotion and resampling policy are not implemented. All records have `granularity='daily'` and `quality='true'` (or NULL if below detection threshold).

- **Monthly Archive Snapshots** (User Story 6 - partial): Archive configuration exists in `googili.toml` but ArchiveService is not yet implemented. Operators can manually export data using SQL queries.

- **Scheduled Daemon Mode**: The simplified main.py does not implement APScheduler or daemon mode. Operators must run ingestion manually or configure external cron.

- **Multi-Mode CLI**: Removed `--daily`, `--manual`, `--daemon`, `--backfill` flags. Single command `python main.py` performs ingestion.

### Configuration Reference

**googili.toml structure**:
```toml
[general]
province = "TH"  # Thailand-wide (changed from TH-50 Chiang Mai)
language = "en-US"  # Google Trends interface language
timezone = "Asia/Bangkok"

[keywords]
terms = [
  "ไข้",           # Fever
  "ไอ",            # Cough
  "เจ็บคอ",        # Sore throat
  # ... 10 total keywords
]

[schedule]
jitter_seconds = [3, 5]  # Random jitter range (fixed from jitter_minutes bug)

[stitching]
min_overlap_days = 1  # Minimum overlap (warn if <3)
trim_percent = 20     # Trim percentage for robust scaling (0-50)

[rate_limiting]
max_retries = 3
backoff_base_seconds = 60
backoff_multiplier = 5.0
max_backoff_seconds = 1800
respect_retry_after = true
```
