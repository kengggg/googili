# Data Model: Fetcher Core

**Feature**: Fetcher Core - Google Trends RSV Data Ingestion
**Date**: 2025-11-04

## Overview

The Fetcher core stores three primary entities in SQLite: RSV Records (time-series data), Batch Events (provenance), and Keyword Configuration (scope). All timestamps use Asia/Bangkok (ICT) timezone.

---

## Entity Definitions

### 1. RSV Record

**Purpose**: Represents a single (keyword, date) observation of Google Trends RSV with stitching and quality metadata.

**Attributes**:
- `keyword` (TEXT, required): Thai search term (e.g., "ไข้")
- `date` (DATE, required): Observation date in ICT
- `rsv_raw` (INTEGER, 0-100, required): Raw RSV from Google Trends request
- `source_window_start` (DATE, required): Start date of request window used
- `fetched_at_ict` (TIMESTAMP, required): When this record was retrieved
- `rsv_stitched` (REAL, nullable): Scaled RSV value after overlap-based stitching
- `batch_id` (TEXT, required): Foreign key to Batch Event
- `granularity` (TEXT, required): `daily` or `weekly` (source data granularity)
- `impute_method` (TEXT, nullable): `weekly_flat` if promoted from weekly, else NULL
- `quality` (TEXT, required): `true` (daily) or `coarse` (weekly-derived)

**Constraints**:
- PRIMARY KEY: `(keyword, date)` - ensures idempotence
- CHECK: `rsv_raw >= 0 AND rsv_raw <= 100`
- CHECK: `granularity IN ('daily', 'weekly')`
- CHECK: `quality IN ('true', 'coarse')`
- FOREIGN KEY: `batch_id` references `events_raw_rsv_ingested(batch_id)`

**Relationships**:
- Many RSV Records → One Batch Event (batch_id)

**Validation Rules**:
- If `granularity='weekly'`, then `impute_method='weekly_flat'` and `quality='coarse'`
- If `granularity='daily'`, then `impute_method IS NULL` and `quality='true'`
- `rsv_stitched IS NULL` only if below detection threshold

**State Transitions**:
- Initial insert: `rsv_raw` populated, `rsv_stitched=NULL` (before stitching)
- After stitching: `rsv_stitched` updated to scaled value
- On backfill: UPSERT may update existing record (logged in batch event)

---

### 2. Batch Event

**Purpose**: Represents a single ingestion run with complete provenance metadata for audit trail.

**Attributes**:
- `batch_id` (TEXT, required, PRIMARY KEY): Unique identifier (e.g., "batch_20251104_073215")
- `requested_keywords` (TEXT, required): JSON array of keywords requested
- `requested_window` (TEXT, required): Date range (e.g., "2025-11-03 to 2025-11-04")
- `rows_written` (INTEGER, required): Total RSV records created/updated
- `true_daily_count` (INTEGER, required): Count of `quality='true'` records
- `weekly_flat_count` (INTEGER, required): Count of `quality='coarse'` records
- `missing_count` (INTEGER, required): Count of below-detection days
- `status` (TEXT, required): `success`, `degraded`, or `fail`
- `started_at_ict` (TIMESTAMP, required): Batch start time
- `finished_at_ict` (TIMESTAMP, nullable): Batch end time (NULL if crashed)
- `notes` (TEXT, nullable): Human-readable notes (e.g., "all-zeros for keyword X", "stitching degraded")

**Constraints**:
- PRIMARY KEY: `batch_id`
- CHECK: `status IN ('success', 'degraded', 'fail')`
- CHECK: `rows_written = true_daily_count + weekly_flat_count`

**Relationships**:
- One Batch Event ← Many RSV Records

**Validation Rules**:
- `status='success'` requires `rows_written > 0`
- `status='fail'` requires `notes` describing error
- `finished_at_ict >= started_at_ict` (if not NULL)

**State Transitions**:
- Created: `started_at_ict` set, `status='pending'` (not persisted; in-memory only)
- On success: `finished_at_ict` set, `status='success'`, counts populated
- On failure: `finished_at_ict` set, `status='fail'`, `notes` describe error

---

### 3. Keyword Configuration

**Purpose**: Represents an active Thai keyword tracked for Chiang Mai Province.

**Attributes**:
- `term` (TEXT, required, PRIMARY KEY): Thai search keyword
- `active` (BOOLEAN, required, default TRUE): Whether to fetch this keyword
- `created_at` (TIMESTAMP, required): When keyword was added
- `province_code` (TEXT, required, default 'TH-50'): ISO 3166-2 code (Chiang Mai)

**Constraints**:
- PRIMARY KEY: `term`
- CHECK: `province_code = 'TH-50'` (MVP constraint)

**Relationships**:
- Referenced by RSV Records (keyword attribute)

**Validation Rules**:
- `term` must be non-empty Thai string (validated at config load)
- Inactive keywords (`active=FALSE`) skipped during ingestion but retained for audit

**State Transitions**:
- Added: `created_at` set, `active=TRUE`
- Deprecated: `active` set to FALSE (historical data retained)

---

## Relationships Diagram

```
┌─────────────────────────┐
│  Keyword Configuration  │
│  (config_keywords)      │
│  - term (PK)            │
│  - active               │
│  - province_code        │
└──────────┬──────────────┘
           │
           │ referenced by
           │
           ↓
┌─────────────────────────┐
│     RSV Record          │
│  (raw_trenddata)        │
│  - keyword (PK)         │◄───┐
│  - date (PK)            │    │
│  - rsv_raw              │    │
│  - rsv_stitched         │    │ Many-to-One
│  - batch_id (FK)        │────┤
│  - granularity          │    │
│  - quality              │    │
└─────────────────────────┘    │
                               │
                               │
┌─────────────────────────┐    │
│     Batch Event         │    │
│  (events_raw_rsv_       │    │
│   ingested)             │    │
│  - batch_id (PK)        │◄───┘
│  - requested_keywords   │
│  - rows_written         │
│  - status               │
│  - started_at_ict       │
│  - finished_at_ict      │
└─────────────────────────┘
```

---

## Data Integrity Rules

### Idempotence (Constitution Requirement)
- PRIMARY KEY on `(keyword, date)` prevents duplicate records
- UPSERT pattern: `INSERT OR REPLACE` allows safe reruns
- Batch events append-only (never updated after `finished_at_ict` set)

### Append-Only Semantics
- RSV Records: UPSERT only during explicit backfill/repair (logged in batch event)
- Batch Events: Never modified after creation (immutable audit trail)
- Keyword Configuration: Deprecation via `active=FALSE` (never deleted)

### Referential Integrity
- Each RSV Record MUST reference valid `batch_id`
- Orphan RSV records (batch event deleted) indicate data corruption
- Foreign key constraint ON DELETE RESTRICT prevents batch event deletion

### Timezone Consistency (Constitution Requirement)
- All TIMESTAMP columns stored in ICT (Asia/Bangkok)
- SQLite stores as ISO 8601 strings with +07:00 offset
- Application enforces timezone at creation (never UTC)

---

## Indexes for Performance

```sql
-- Primary query: Visualiser fetches recent data per keyword
CREATE INDEX idx_rsv_keyword_date ON raw_trenddata(keyword, date DESC);

-- Provenance queries: Trace batch lineage
CREATE INDEX idx_rsv_batch ON raw_trenddata(batch_id);

-- Health queries: Latest successful fetch
CREATE INDEX idx_events_finished ON events_raw_rsv_ingested(finished_at_ict DESC);

-- Quality filtering: Exclude coarse records from stitching
CREATE INDEX idx_rsv_quality ON raw_trenddata(quality) WHERE quality = 'true';
```

---

## Archive Schema (Monthly Snapshots)

**CSV Format** (./archive/YYYY-MM/raw_trenddata.csv):
```
keyword,date,rsv_raw,rsv_stitched,granularity,quality,batch_id,fetched_at_ict
ไข้,2025-11-04,45,43.2,daily,true,batch_20251104_073215,2025-11-04T07:32:15+07:00
```

**Data Dictionary** (./archive/YYYY-MM/README.txt):
- Describes all columns, constraints, and quality flags
- Includes month's batch event summary
- References constitution version used for that month's data

---

## Migration Path (Future)

**SQLite → PostgreSQL** (when scaling beyond MVP):
1. Export all tables to CSV via `sqlite3 .dump`
2. Create PostgreSQL schema with equivalent constraints
3. Import CSVs with `COPY` command
4. Update application connection string
5. Verify data integrity via count checks and sample queries

**Schema Versioning**:
- Add `schema_version` column to Batch Event table
- Current version: `v1.0` (MVP)
- Future migrations tracked via Alembic or Flyway

---

## Validation Checklist

- [ ] All PRIMARY KEY and UNIQUE constraints defined
- [ ] All FOREIGN KEY relationships enforced
- [ ] All CHECK constraints validate business rules
- [ ] All TIMESTAMP columns use Asia/Bangkok timezone
- [ ] Indexes exist for common query patterns
- [ ] Archive format documented with data dictionary
- [ ] Migration path to PostgreSQL documented

**Status**: ✅ Complete and aligned with Googili constitution v1.1.0
