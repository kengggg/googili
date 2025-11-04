# Feature Specification: Fetcher Core - Google Trends RSV Data Ingestion

**Feature Branch**: `001-fetcher-core`
**Created**: 2025-11-04
**Status**: Draft
**Input**: User description: "Fetcher core for Google Trends RSV data ingestion with stitching, provenance, and event emission"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Daily RSV Data Availability (Priority: P1)

SAT operators and analysts need reliable, up-to-date Google Trends search volume data for ~10 Thai ILI-related keywords in Chiang Mai Province to support their weekly surveillance huddles and early warning assessments.

**Why this priority**: This is the foundational capability that enables all downstream analysis and alerting. Without reliable daily data ingestion, the entire surveillance system cannot function.

**Independent Test**: Can be fully tested by scheduling a daily ingestion run, verifying that RSV data appears in the database for all configured keywords by the expected morning check time, and confirming that batch event records are created with correct metadata.

**Acceptance Scenarios**:

1. **Given** the system is configured with 10 Thai keywords for Chiang Mai, **When** the daily scheduled ingestion runs at 07:00 ICT, **Then** RSV data for all 10 keywords is retrieved and stored with timestamps, window metadata, and batch IDs within 10 minutes.

2. **Given** a successful daily ingestion, **When** operators check the Data Health widget, **Then** they see the "last successful fetch" timestamp showing today's date and the count of rows written.

3. **Given** an operator needs to manually trigger data collection, **When** they initiate an on-demand ingestion run, **Then** the system fetches current RSV data and creates a new batch event marked as "manual trigger."

---

### User Story 2 - Historical Context via 90-Day Backfill (Priority: P1)

On first deployment, analysts need ~90 days of historical Google Trends data to establish baseline patterns and enable meaningful anomaly detection from day one.

**Why this priority**: Without historical context, the Analyser cannot compute baselines or identify unusual patterns. This is essential for the system to be operationally useful immediately after deployment.

**Independent Test**: Can be tested by running the system for the first time on a clean database and verifying that exactly 90 days of RSV data (or the maximum available if less than 90 days) is retrieved for each keyword, properly stitched, and stored with provenance metadata.

**Acceptance Scenarios**:

1. **Given** a clean database with no existing RSV data, **When** the first ingestion run executes, **Then** the system automatically triggers a 90-day backfill for all configured keywords and marks the batch event as "initial backfill."

2. **Given** the 90-day backfill completes successfully, **When** analysts review the data, **Then** they see a continuous daily time series spanning 90 days (or maximum available) with no duplicate (keyword, date) pairs.

3. **Given** the backfill encounters a keyword with insufficient history, **When** the backfill completes, **Then** the system stores all available days and logs a note in the batch event indicating "partial backfill: only N days available."

---

### User Story 3 - Continuous Time Series via Stitching (Priority: P1)

Analysts need a stable, research-grade daily time series where RSV values remain comparable across days despite Google Trends' independent normalization of each request window.

**Why this priority**: Without stitching, the raw RSV values will jump unpredictably due to normalization artifacts, making the data unusable for trend analysis and undermining trust in the system.

**Independent Test**: Can be tested by running multiple daily ingestions with overlapping windows, verifying that the stitched RSV values maintain level consistency (no jumps solely due to normalization), and confirming that the scaling factors are computed and applied correctly.

**Acceptance Scenarios**:

1. **Given** day N's data is already stored, **When** day N+1's ingestion runs with a window overlapping day N by at least 1 day, **Then** the system computes a robust scaling factor from the overlap and applies it before publishing the stitched RSV values.

2. **Given** a stitched time series exists, **When** analysts examine consecutive days with stable search behavior, **Then** they observe RSV values that do not show level jumps attributable to normalization differences.

3. **Given** an overlap contains outlier days (single-day spikes), **When** the scaling factor is computed, **Then** the algorithm down-weights the outliers to prevent them from distorting the stitching.

---

### User Story 4 - Gap Recovery After Outages (Priority: P2)

When ingestion fails for more than 24 hours due to network issues or API unavailability, operators need the system to automatically detect and fill data gaps without creating duplicates.

**Why this priority**: Operational resilience is critical for a surveillance system, but this is secondary to the core daily ingestion capability.

**Independent Test**: Can be tested by simulating a 3-day outage, restarting the system, and verifying that a 14-day rolling backfill automatically triggers, fills the gaps, restitches overlaps, and creates no duplicate records.

**Acceptance Scenarios**:

1. **Given** ingestion has been offline for 48+ hours, **When** the system restarts and detects the gap, **Then** it automatically triggers a 14-day rolling backfill to fill missing days and restitch overlaps.

2. **Given** the recovery backfill completes, **When** operators review the data, **Then** they see a continuous time series with no duplicate (keyword, date) pairs and a batch event marked "recovery backfill."

3. **Given** the recovery backfill encounters some days with missing data, **When** those days cannot be retrieved even with wider windows, **Then** the system follows the resampling policy (promote to weekly if ≥3-day run) and flags them appropriately.

---

### User Story 5 - Data Quality Transparency via Granularity Badges (Priority: P2)

Analysts need to instantly distinguish between "true daily" RSV values and "weekly-derived coarse" values when reviewing the time series, so they can adjust their interpretation appropriately.

**Why this priority**: Interpretive clarity is essential for public health decision-making, but the system can function with basic daily data before adding granularity badges.

**Independent Test**: Can be tested by creating scenarios with missing daily data that trigger weekly promotion, then verifying that the Data Health widget and data records correctly display badges indicating "true_daily," "weekly_flat," or "missing" status.

**Acceptance Scenarios**:

1. **Given** a keyword has a 4-day run of missing daily data, **When** the resampling logic promotes to weekly, **Then** those 4 days are marked with granularity=weekly, impute_method=weekly_flat, and quality=coarse in the database.

2. **Given** the Data Health widget displays the time series, **When** analysts hover over or view days, **Then** they see clear badges indicating whether each day is "true_daily," "weekly_flat," or "missing."

3. **Given** a batch summary is generated, **When** operators review it for their weekly huddle, **Then** they see counts of true_daily vs. weekly_flat vs. missing rows to assess data quality at a glance.

---

### User Story 6 - Provenance & Audit Trail for Governance (Priority: P3)

Program stewards and researchers need complete provenance metadata (batch IDs, fetch timestamps, window parameters, row counts) to support governance reviews, quarterly assessments, and academic reporting.

**Why this priority**: Auditability is important for long-term trust and research use, but it's not required for the system's core operational function.

**Independent Test**: Can be tested by running several ingestion batches (daily, backfill, manual), then verifying that each batch event is recorded with complete metadata and can be traced to specific RSV records via batch_id.

**Acceptance Scenarios**:

1. **Given** multiple ingestion runs over time, **When** stewards export the batch event log, **Then** they see a complete audit trail with batch_id, start/end timestamps, keywords requested, window parameters, row counts, and status for each run.

2. **Given** a specific RSV record, **When** researchers query its lineage, **Then** they can trace it back to the exact batch event, including the fetch timestamp and request window used.

3. **Given** monthly archive snapshots are configured, **When** the end of the month is reached, **Then** the system saves an immutable copy of all batch events and RSV records to ./archive with a data dictionary explaining the schema.

---

### Edge Cases

- **What happens when Google Trends returns all zeros for a keyword across multiple days?**
  The system marks those days with granularity=daily, quality=true (if daily), and logs a "zero-rate warning" in the batch event notes. If the zeros span ≥3 consecutive days, they trigger a Data Health alert visible to operators.

- **What happens when the overlap window between consecutive fetches contains no matching days?**
  The system detects the stitching failure, logs an integrity warning in the batch event, and falls back to storing the raw (unstitched) values while alerting operators via the Data Health widget.

- **What happens when an on-demand manual fetch is triggered while a scheduled daily fetch is running?**
  The system queues the manual fetch to run after the current batch completes, preventing concurrent writes and ensuring append-only integrity.

- **What happens when a keyword is removed from the configuration mid-deployment?**
  Historical data for that keyword remains in the database (append-only), but future ingestions skip it. A batch event note records "keyword deprecated: [name]."

- **What happens when a backfill or resampling operation needs to retrieve weekly RSV data but even weekly is unavailable?**
  The system does not impute or interpolate. It leaves those days unpublished (null/missing) and raises a Data Health warning: status=below_detection.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST fetch daily Google Trends RSV (0–100) for all configured Thai keywords scoped to Chiang Mai Province on a daily schedule (default 07:00 ICT).

- **FR-002**: System MUST support on-demand manual ingestion runs triggered by operators for verification or recovery purposes.

- **FR-003**: System MUST perform a one-time 90-day historical backfill on first deployment to initialize the time series.

- **FR-004**: System MUST automatically trigger a 14-day rolling backfill when ingestion has been offline for more than 24 hours.

- **FR-005**: System MUST stitch overlapping request windows using a robust scaling factor that down-weights outliers to produce a stable, continuous daily time series.

- **FR-006**: System MUST ensure no duplicate (keyword, date) pairs exist in the published data, enforcing append-only semantics.

- **FR-007**: System MUST store raw RSV values, stitched RSV values, fetch timestamps, source window parameters, and batch IDs for every record.

- **FR-008**: System MUST emit an "ingestion complete" event after each batch, recording batch_id, status (success/degraded/fail), start/end timestamps, row counts, and notes.

- **FR-009**: System MUST implement the sparse-day resampling policy: (1) re-fetch with wider window, (2) promote to weekly if ≥3-day run, (3) mark as below_detection if weekly unavailable.

- **FR-010**: System MUST flag records with granularity (daily/weekly), impute_method (nullable or "weekly_flat"), and quality (true/coarse) to support analyst interpretation.

- **FR-011**: System MUST exclude coarse (weekly-derived) records from future stitching factor computations to prevent normalization drift.

- **FR-012**: System MUST publish Data Health metrics including last successful fetch timestamp, last batch row count, zero-rate warnings, and stitching integrity alerts.

- **FR-013**: System MUST save monthly archive snapshots of batch events and RSV records to ./archive directory with a data dictionary.

- **FR-014**: System MUST read all operational parameters (keywords, geography, baseline defaults, archive cadence) from a single configuration file with no in-app UI editing.

- **FR-015**: System MUST enforce zero values remain zero (no manufactured signal) unless a subsequent re-fetch with daily granularity yields non-zero values.

### Key Entities

- **RSV Record**: Represents a single (keyword, date) observation with raw RSV value (0–100), stitched RSV value, source window used, fetch timestamp (Asia/Bangkok), batch ID, granularity flag, impute method, and quality flag.

- **Batch Event**: Represents a single ingestion run with unique batch_id, requested keywords, requested window parameters, rows written, status (success/degraded/fail), start/end timestamps (ICT), notes (anomaly flags), and counts of true_daily/weekly_flat/missing records.

- **Keyword Configuration**: Represents a Thai symptom keyword (e.g., ไข้, ไอ, เจ็บคอ) with its scope (Chiang Mai TH-50), active status, and provenance notes. Managed in a version-controlled configuration file.

- **Data Health Status**: Represents current operational health with last successful fetch timestamp, last batch size, zero-rate warnings, stitching integrity flags, and granularity breakdown for display in the Visualiser's Data Health widget.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Daily RSV data for all configured keywords is available and visible to operators by morning check time (08:00 ICT) on 99% of scheduled days during pilot.

- **SC-002**: Zero duplicate (keyword, date) records exist in the published time series across all ingestion runs (daily, backfill, manual).

- **SC-003**: The 90-day initial backfill completes within 15 minutes on first deployment for 10 keywords on modest hardware.

- **SC-004**: Stitched time series shows no level jumps exceeding 20% on consecutive days with stable search behavior (validated against test scenarios with controlled overlaps).

- **SC-005**: After a simulated 72-hour outage, the 14-day rolling backfill successfully fills all gaps and restitches overlaps with zero duplicates within 10 minutes.

- **SC-006**: Operators can distinguish between true daily data and weekly-derived coarse data by viewing granularity badges in the Data Health widget with zero ambiguity.

- **SC-007**: 100% of batch events include complete provenance metadata (batch_id, timestamps, window, row counts, status) for audit trail.

- **SC-008**: Pilot participants rate the data's "clarity to interpret" and "timeliness" as "high" or "very high" on feasibility survey items (≥80% positive ratings).

- **SC-009**: Monthly archive snapshots are generated automatically at month-end and include a data dictionary explaining all schema fields.

- **SC-010**: Field pilot demonstrates ≥99% fetch success rate per week with clear visibility of any degraded batches via Data Health widget.

### Assumptions

- Google Trends API/interface remains stable and accessible during pilot (no major algorithmic or access changes).
- Network connectivity between the system and Google Trends is reliable with occasional brief outages (<24 hours).
- ~10 Thai keywords are sufficient for initial Chiang Mai ILI surveillance; keyword list refinement will occur post-pilot.
- Operators have access to the Data Health widget through the Visualiser core (separate feature).
- The system runs on modest hardware with sufficient storage for 90+ days of daily records for 10 keywords.
- Structured logging (JSON) is configured and retained for troubleshooting and governance reviews.
- All timestamps use Asia/Bangkok (ICT) timezone for consistency with local public health workflows.

### Dependencies

- **Visualiser Core**: Provides the Data Health widget that displays fetch timestamps, granularity badges, and integrity warnings.
- **Configuration System**: Single configuration file exists and is version-controlled (managed separately or as part of this feature).
- **Database Layer**: SQLite with WAL mode is set up and accessible for append-only writes and event storage.
- **Scheduler**: Cron or equivalent scheduling mechanism is available to trigger daily ingestion at 07:00 ICT.
- **Google Trends Access**: API key, scraping library, or interface for retrieving RSV data is available and compliant with terms of use.
