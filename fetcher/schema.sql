-- GOOGILI Fetcher Core - SQLite Database Schema
-- Constitution-aligned: Append-only events, idempotent writes, WAL mode
-- Version: 1.0 (MVP)
-- Date: 2025-11-04

-- Enable WAL mode for concurrent reads (Visualiser/Analyser) during Fetcher writes
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

-- ========================================
-- Table: raw_trenddata
-- Purpose: Time-series RSV data with stitching and quality metadata
-- Primary Key: (keyword, date) enforces idempotence
-- ========================================

CREATE TABLE IF NOT EXISTS raw_trenddata (
    keyword TEXT NOT NULL,
    date DATE NOT NULL,
    rsv_raw INTEGER NOT NULL CHECK(rsv_raw >= 0 AND rsv_raw <= 100),
    source_window_start DATE NOT NULL,
    fetched_at_ict TIMESTAMP NOT NULL,
    rsv_stitched REAL,  -- NULL if below detection or before stitching
    batch_id TEXT NOT NULL,
    granularity TEXT NOT NULL CHECK(granularity IN ('daily', 'weekly')),
    impute_method TEXT CHECK(impute_method IN (NULL, 'weekly_flat')),
    quality TEXT NOT NULL CHECK(quality IN ('true', 'coarse')),

    PRIMARY KEY (keyword, date),
    FOREIGN KEY (batch_id) REFERENCES events_raw_rsv_ingested(batch_id) ON DELETE RESTRICT
);

-- Indexes for common query patterns
CREATE INDEX IF NOT EXISTS idx_rsv_keyword_date ON raw_trenddata(keyword, date DESC);
CREATE INDEX IF NOT EXISTS idx_rsv_batch ON raw_trenddata(batch_id);
CREATE INDEX IF NOT EXISTS idx_rsv_quality ON raw_trenddata(quality) WHERE quality = 'true';
CREATE INDEX IF NOT EXISTS idx_rsv_fetched ON raw_trenddata(fetched_at_ict DESC);

-- ========================================
-- Table: events_raw_rsv_ingested
-- Purpose: Append-only batch event log for provenance
-- Primary Key: batch_id (unique per run)
-- ========================================

CREATE TABLE IF NOT EXISTS events_raw_rsv_ingested (
    batch_id TEXT NOT NULL PRIMARY KEY,
    batch_type TEXT NOT NULL CHECK(batch_type IN ('daily', 'initial_backfill', 'recovery_backfill', 'manual', 'ingestion')),
    requested_keywords TEXT NOT NULL,  -- JSON array: ["ไข้", "ไอ", ...]
    requested_window TEXT NOT NULL,    -- "2025-11-03 to 2025-11-04"
    started_at_ict TIMESTAMP NOT NULL,
    finished_at_ict TIMESTAMP,  -- NULL if crashed before completion or still running
    status TEXT NOT NULL CHECK(status IN ('running', 'success', 'degraded', 'fail')),
    rows_written INTEGER NOT NULL DEFAULT 0 CHECK(rows_written >= 0),
    rows_updated INTEGER NOT NULL DEFAULT 0 CHECK(rows_updated >= 0),
    rows_missing INTEGER NOT NULL DEFAULT 0 CHECK(rows_missing >= 0),
    quality_true_daily INTEGER CHECK(quality_true_daily >= 0),
    quality_weekly_flat INTEGER CHECK(quality_weekly_flat >= 0),
    quality_below_detection INTEGER CHECK(quality_below_detection >= 0),
    notes TEXT,  -- Audit context: stitching factors, warnings, manual notes
    error_message TEXT  -- Error details if status='fail'
);

-- Index for health queries (last successful fetch)
CREATE INDEX IF NOT EXISTS idx_events_finished ON events_raw_rsv_ingested(finished_at_ict DESC);
CREATE INDEX IF NOT EXISTS idx_events_status ON events_raw_rsv_ingested(status);

-- ========================================
-- Table: config_keywords
-- Purpose: Active keywords for ingestion (loaded from TOML at startup)
-- Primary Key: term
-- ========================================

CREATE TABLE IF NOT EXISTS config_keywords (
    term TEXT PRIMARY KEY,
    active BOOLEAN NOT NULL DEFAULT 1,
    created_at TIMESTAMP NOT NULL,
    province_code TEXT NOT NULL DEFAULT 'TH-50',
    notes TEXT,  -- Optional notes about keyword (e.g., synonym info, deprecation reason)

    CHECK(province_code = 'TH-50')  -- MVP: Chiang Mai only
);

-- ========================================
-- Table: health_probe (ephemeral; for /healthz DB writability test)
-- Purpose: Lightweight probe table for health endpoint
-- ========================================

CREATE TABLE IF NOT EXISTS health_probe (
    probe_id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Periodically clean old probes (keep last 10)
CREATE TRIGGER IF NOT EXISTS cleanup_health_probe
AFTER INSERT ON health_probe
BEGIN
    DELETE FROM health_probe WHERE probe_id < (SELECT MAX(probe_id) - 10 FROM health_probe);
END;

-- ========================================
-- Views for Common Queries
-- ========================================

-- Latest batch summary (for /healthz endpoint)
CREATE VIEW IF NOT EXISTS v_latest_batch AS
SELECT
    batch_id,
    status,
    finished_at_ict AS last_fetch,
    rows_written,
    quality_true_daily AS true_daily_count,
    quality_weekly_flat AS weekly_flat_count,
    rows_missing AS missing_count,
    notes
FROM events_raw_rsv_ingested
WHERE finished_at_ict IS NOT NULL
ORDER BY finished_at_ict DESC
LIMIT 1;

-- Recent RSV data per keyword (for Visualiser)
CREATE VIEW IF NOT EXISTS v_recent_rsv AS
SELECT
    keyword,
    date,
    rsv_stitched,
    granularity,
    quality,
    fetched_at_ict
FROM raw_trenddata
WHERE date >= date('now', '-90 days')  -- 90-day window
ORDER BY keyword, date DESC;

-- Data quality summary (for Data Health widget)
CREATE VIEW IF NOT EXISTS v_data_quality AS
SELECT
    keyword,
    COUNT(*) AS total_days,
    SUM(CASE WHEN quality = 'true' THEN 1 ELSE 0 END) AS true_daily_count,
    SUM(CASE WHEN quality = 'coarse' THEN 1 ELSE 0 END) AS coarse_count,
    MAX(date) AS latest_date,
    MAX(fetched_at_ict) AS last_updated
FROM raw_trenddata
WHERE date >= date('now', '-90 days')
GROUP BY keyword;

-- ========================================
-- Seed Data (Example Keywords - Replace with actual TOML config)
-- ========================================

-- Note: In production, config_keywords populated from googili.toml at startup
-- This is for reference/testing only

INSERT OR IGNORE INTO config_keywords (term, active, created_at, province_code) VALUES
('ไข้', 1, CURRENT_TIMESTAMP, 'TH-50'),    -- Fever
('ไอ', 1, CURRENT_TIMESTAMP, 'TH-50'),     -- Cough
('เจ็บคอ', 1, CURRENT_TIMESTAMP, 'TH-50'), -- Sore throat
('น้ำมูก', 1, CURRENT_TIMESTAMP, 'TH-50'), -- Runny nose
('ปวดศีรษะ', 1, CURRENT_TIMESTAMP, 'TH-50'), -- Headache
('เหนื่อย', 1, CURRENT_TIMESTAMP, 'TH-50'), -- Fatigue
('ปวดกล้ามเนื้อ', 1, CURRENT_TIMESTAMP, 'TH-50'), -- Muscle pain
('อาเจียน', 1, CURRENT_TIMESTAMP, 'TH-50'), -- Vomiting
('ท้องเสีย', 1, CURRENT_TIMESTAMP, 'TH-50'), -- Diarrhea
('หายใจลำบาก', 1, CURRENT_TIMESTAMP, 'TH-50'); -- Shortness of breath

-- ========================================
-- Contract Validation Queries (for testing)
-- ========================================

-- Test 1: Verify no duplicate (keyword, date) pairs
-- Expected: 0 rows
SELECT keyword, date, COUNT(*) as dup_count
FROM raw_trenddata
GROUP BY keyword, date
HAVING COUNT(*) > 1;

-- Test 2: Verify all RSV records have valid batch events
-- Expected: 0 rows (no orphans)
SELECT r.keyword, r.date, r.batch_id
FROM raw_trenddata r
LEFT JOIN events_raw_rsv_ingested e ON r.batch_id = e.batch_id
WHERE e.batch_id IS NULL;

-- Test 3: Verify quality flags consistent with granularity
-- Expected: 0 rows (all daily=true, all weekly=coarse)
SELECT keyword, date, granularity, quality
FROM raw_trenddata
WHERE (granularity = 'daily' AND quality != 'true')
   OR (granularity = 'weekly' AND quality != 'coarse');

-- Test 4: Verify batch event row counts match actual records
-- Expected: 0 rows (counts accurate)
SELECT
    e.batch_id,
    e.rows_written AS event_count,
    COUNT(r.keyword) AS actual_count,
    e.rows_written - COUNT(r.keyword) AS diff
FROM events_raw_rsv_ingested e
LEFT JOIN raw_trenddata r ON e.batch_id = r.batch_id
GROUP BY e.batch_id
HAVING e.rows_written != COUNT(r.keyword);

-- ========================================
-- Schema Version Tracking
-- ========================================

-- Add schema_version column to events table for future migrations
-- Current version: v1.0 (MVP)
-- ALTER TABLE events_raw_rsv_ingested ADD COLUMN schema_version TEXT DEFAULT 'v1.0';

-- ========================================
-- Notes for Downstream Cores (Analyser, Visualiser)
-- ========================================

-- Analyser Contract:
-- - Read from raw_trenddata WHERE quality = 'true' (exclude coarse records from baselines)
-- - Read from events_raw_rsv_ingested for last fetch timestamp
-- - Write analysis results to separate tables (not defined here)

-- Visualiser Contract:
-- - Read from v_latest_batch for Data Health widget
-- - Read from v_recent_rsv for time-series charts
-- - Read from v_data_quality for granularity badges
-- - Read from events_raw_rsv_ingested WHERE status != 'success' for alerts

-- Migration Path to PostgreSQL:
-- 1. Export: sqlite3 googili.db .dump > schema.sql
-- 2. Convert SQLite-specific syntax (AUTOINCREMENT → SERIAL, CHECK → CONSTRAINT)
-- 3. Import to Postgres: psql -d googili -f schema_pg.sql
-- 4. Verify foreign keys, indexes, views

-- ========================================
-- End of Schema
-- ========================================
