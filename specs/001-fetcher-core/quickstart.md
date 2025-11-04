# Quickstart: Fetcher Core Operator Runbook

**Feature**: Fetcher Core - Google Trends RSV Data Ingestion
**Date**: 2025-11-04
**Target Audience**: System operators, SAT staff, technical stewards

## Purpose

This runbook provides step-by-step instructions for deploying, operating, and troubleshooting the Googili Fetcher core. All operations assume a Linux server with Docker installed.

---

## Prerequisites

**Required**:
- Linux server (Ubuntu 20.04+ or equivalent)
- Docker 20.10+ and Docker Compose 2.0+
- 2 CPU cores, 4GB RAM, 20GB storage
- Internet access to Google Trends

**Optional**:
- Domain name for `/healthz` endpoint (if monitoring externally)
- Log aggregation system (ELK, Loki) for structured JSON logs

---

## Initial Setup

### Step 1: Prepare Directories

```bash
# Create project structure
mkdir -p ~/googili
cd ~/googili
mkdir -p data archive config

# Set permissions (Docker user needs write access)
chmod 755 data archive config
```

### Step 2: Create Configuration File

Create `config/googili.toml` with your keywords and settings:

```toml
[general]
province = "TH-50"  # Chiang Mai
timezone = "Asia/Bangkok"

[keywords]
terms = [
  "ไข้",           # Fever
  "ไอ",            # Cough
  "เจ็บคอ",        # Sore throat
  "น้ำมูก",        # Runny nose
  "ปวดศีรษะ",      # Headache
  "เหนื่อย",       # Fatigue
  "ปวดกล้ามเนื้อ", # Muscle pain
  "อาเจียน",       # Vomiting
  "ท้องเสีย",      # Diarrhea
  "หายใจลำบาก"     # Shortness of breath
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
trim_percent = 20

[resampling]
min_run_for_weekly = 3

[archive]
output_dir = "./data/archive"
cadence = "monthly"

[health]
port = 8080
db_probe_timeout_seconds = 3
```

### Step 3: Create docker-compose.yml

Create `docker-compose.yml` in project root:

```yaml
services:
  fetcher:
    image: googili/fetcher:latest  # Or build: ./fetcher for local build
    container_name: googili_fetcher
    environment:
      - TZ=Asia/Bangkok
      - LOG_LEVEL=INFO
      - PYTHONUNBUFFERED=1
    volumes:
      - ./data:/app/data          # SQLite database + archives
      - ./config:/app/config:ro   # Read-only config
    ports:
      - "8080:8080"  # /healthz endpoint
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8080/healthz"]
      interval: 30s
      timeout: 3s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    networks:
      - googili_net

networks:
  googili_net:
    driver: bridge
```

### Step 4: Start Fetcher

```bash
# Pull latest image (or build locally)
docker compose pull fetcher

# Start in detached mode
docker compose up -d fetcher

# Verify healthy status
docker compose ps
# Expected: googili_fetcher "healthy"

# Check logs for first-run backfill
docker compose logs -f fetcher
# Expected: "Starting 90-day backfill... rows written: 900 (10 keywords × 90 days)"
```

**First Run**: The Fetcher automatically detects an empty database and triggers a 90-day backfill. This takes ~5-10 minutes.

---

## Daily Operations

### Verifying Daily Ingestion

**Target**: Daily ingestion completes by 07:30 ICT ± 5 min jitter

```bash
# Check last batch event
docker exec googili_fetcher sqlite3 /app/data/googili.db \
  "SELECT batch_id, status, finished_at_ict, rows_written FROM events_raw_rsv_ingested ORDER BY finished_at_ict DESC LIMIT 1"

# Expected output:
# batch_20251104_073215|success|2025-11-04 07:32:15|10
```

### Checking Health Status

```bash
# Via curl (from host)
curl http://localhost:8080/healthz | jq

# Expected JSON:
# {
#   "status": "success",
#   "last_fetch": "2025-11-04T07:32:15+07:00",
#   "last_batch_id": "batch_20251104_073215",
#   "rows_written": 10,
#   "true_daily": 10,
#   "weekly_flat": 0,
#   "missing": 0,
#   "db_writable": true
# }
```

**Health States**:
- `200 OK` + `status: success`: Normal operation
- `200 OK` + `status: degraded`: Last fetch >24h ago, recovery backfill may trigger
- `503 Service Unavailable`: Critical failure (DB locked, scheduler crashed)

### Viewing Logs

```bash
# Tail recent logs
docker compose logs -f fetcher --tail=50

# Search for errors
docker compose logs fetcher | grep ERROR

# View structured JSON logs
docker exec googili_fetcher cat /app/logs/fetcher.log | jq '.message'
```

---

## Recovery Procedures

### After Outage (>24 Hours)

**Symptom**: `/healthz` shows `last_fetch` more than 24 hours ago.

**Automatic Recovery**: On next container restart, Fetcher detects the gap and triggers a 14-day rolling backfill.

**Manual Recovery**:
```bash
# Restart container to trigger automatic backfill
docker compose restart fetcher

# Or manually invoke backfill (if container running)
docker exec googili_fetcher python -m googili.fetcher backfill --days=14

# Verify backfill completed
docker exec googili_fetcher sqlite3 /app/data/googili.db \
  "SELECT COUNT(*) FROM raw_trenddata WHERE date >= date('now', '-14 days')"
# Expected: ~140 records (10 keywords × 14 days)
```

### Database Corruption

**Symptom**: `/healthz` returns `db_writable: false` or container crashes with SQLite errors.

**Recovery**:
```bash
# Stop container
docker compose stop fetcher

# Check database integrity
docker run --rm -v ./data:/data sqlite:latest \
  sqlite3 /data/googili.db "PRAGMA integrity_check;"
# Expected: "ok"

# If corrupted, restore from last monthly archive
cp ./archive/2025-10/googili.db.backup ./data/googili.db

# Restart and backfill missing days
docker compose up -d fetcher
docker exec googili_fetcher python -m googili.fetcher backfill --days=30
```

### Stitching Degraded

**Symptom**: Batch event notes show "stitching degraded" or "no overlap found".

**Cause**: Non-overlapping request windows (rare; usually due to manual backfill misconfiguration).

**Recovery**:
```bash
# Check recent batches for overlap issues
docker exec googili_fetcher sqlite3 /app/data/googili.db \
  "SELECT batch_id, notes FROM events_raw_rsv_ingested WHERE notes LIKE '%stitch%' ORDER BY finished_at_ict DESC LIMIT 5"

# If persistent, trigger full 90-day backfill to rebuild series
docker exec googili_fetcher python -m googili.fetcher backfill --days=90 --force

# Review logs for pytrends errors (API rate limiting, network issues)
docker compose logs fetcher | grep -i "pytrends\|rate limit\|timeout"
```

---

## Maintenance Tasks

### Monthly Archive Check

**Target**: Automatic archive creation at month-end.

```bash
# Verify last month's archive exists
ls -lh ./archive/$(date -d "last month" +%Y-%m)/
# Expected files:
# - raw_trenddata.csv
# - events_raw_rsv_ingested.csv
# - config_keywords.csv
# - README.txt (data dictionary)
```

**If Missing**:
```bash
# Manually trigger archive for specific month
docker exec googili_fetcher python -m googili.fetcher archive --month=2025-10
```

### Config Updates

**Adding/Removing Keywords**:
1. Edit `config/googili.toml` on host
2. Restart container to load new config:
   ```bash
   docker compose restart fetcher
   ```
3. New keywords automatically backfill 90 days on next run
4. Deprecated keywords marked `active=FALSE` in `config_keywords` table (data retained)

**Changing Schedule Time**:
1. Edit `[schedule]` section in `config/googili.toml`
2. Restart container:
   ```bash
   docker compose restart fetcher
   ```
3. Verify new schedule in logs: `"Next scheduled run: 2025-11-05 08:00:00+07:00"`

### Log Rotation

**Automatic**: Docker captures `stdout` logs; configure host logrotate:

```bash
# /etc/logrotate.d/docker-googili
/var/lib/docker/containers/*googili_fetcher*/*.log {
    daily
    rotate 30
    compress
    delaycompress
    notifempty
    copytruncate
}
```

---

## Troubleshooting

### Container Won't Start

**Check Docker Logs**:
```bash
docker compose logs fetcher
```

**Common Issues**:
- **Config parse error**: Validate TOML syntax using `toml-cli` or online validator
- **Port 8080 in use**: Change port in `docker-compose.yml` (e.g., `"8081:8080"`)
- **Volume mount permission**: Ensure `./data` and `./config` are writable by Docker user

### Fetching Fails (pytrends Errors)

**Symptoms**: Batch events with `status=fail`, notes mention "pytrends".

**Diagnosis**:
```bash
# Check pytrends-specific logs
docker compose logs fetcher | grep -i pytrends

# Test Google Trends reachability (inside container)
docker exec googili_fetcher curl -I https://trends.google.com
# Expected: HTTP 200
```

**Common Causes**:
- **Rate limiting**: pytrends hit daily quota (rare; jitter should prevent)
  - **Fix**: Wait 24 hours; next run will retry
- **Network outage**: No internet connectivity
  - **Fix**: Restore network; Fetcher auto-recovers on next schedule
- **Google Trends API change**: pytrends library outdated
  - **Fix**: Update pytrends: `docker exec googili_fetcher pip install --upgrade pytrends`, restart container

### Zero RSV Values (All Keywords)

**Symptoms**: Batch event shows `rows_written=0` or all `rsv_raw=0`.

**Diagnosis**:
```bash
# Check if all keywords returned zeros
docker exec googili_fetcher sqlite3 /app/data/googili.db \
  "SELECT keyword, date, rsv_raw FROM raw_trenddata WHERE date = date('now') ORDER BY keyword"

# Review batch notes for zero-rate warnings
docker exec googili_fetcher sqlite3 /app/data/googili.db \
  "SELECT notes FROM events_raw_rsv_ingested ORDER BY finished_at_ict DESC LIMIT 1"
```

**Possible Causes**:
- **Geographic mismatch**: Config has wrong `province` code (should be `TH-50` for Chiang Mai)
- **Keyword spelling**: Thai keywords typo or Google Trends doesn't track them
- **Genuine low search volume**: Rare but possible (e.g., during low flu season)

**Action**: Review config keywords; consult with SAT team on keyword relevance.

---

## Monitoring & Alerts

### Recommended Alerts

**Critical (Page Operator)**:
- `/healthz` returns 503 for >1 hour
- Last successful fetch >48 hours ago
- Database integrity check fails

**Warning (Email Notification)**:
- Last fetch >24 hours ago (triggers recovery backfill)
- Batch event `status=degraded` for >3 consecutive days
- Weekly_flat_count >30% of rows (data quality degraded)

### Prometheus Integration (Optional)

**Expose Metrics** (future enhancement):
```python
# /metrics endpoint (Prometheus format)
# googili_last_fetch_timestamp
# googili_rows_written_total
# googili_fetch_duration_seconds
```

**Grafana Dashboard** (template):
- Time-series chart: `rows_written` per batch
- Gauge: Hours since last successful fetch
- Bar chart: `true_daily` vs. `weekly_flat` counts

---

## Backup & Disaster Recovery

### Daily Backup

**Automated Script** (run via cron):
```bash
#!/bin/bash
# /usr/local/bin/backup-googili-db.sh

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
cp ~/googili/data/googili.db ~/backups/googili_${TIMESTAMP}.db
gzip ~/backups/googili_${TIMESTAMP}.db

# Retain last 30 days
find ~/backups -name "googili_*.db.gz" -mtime +30 -delete
```

**Cron Entry**:
```
# Daily backup at 02:00 ICT
0 2 * * * /usr/local/bin/backup-googili-db.sh >> /var/log/googili-backup.log 2>&1
```

### Restore from Backup

```bash
# Stop Fetcher
docker compose stop fetcher

# Restore database
gunzip -c ~/backups/googili_20251104_020000.db.gz > ~/googili/data/googili.db

# Restart and verify
docker compose up -d fetcher
curl http://localhost:8080/healthz | jq '.last_fetch'
```

---

## Security Considerations

**Constitution Principle**: No personal data collected (only aggregated RSV values).

**Recommendations**:
- Restrict `/healthz` port to internal network (firewall rule)
- Rotate log files to prevent disk exhaustion
- Regularly review `notes` column for anomalies (e.g., unusual pytrends errors)
- Do NOT log Thai keywords in production (disable via `LOG_LEVEL=INFO` to suppress DEBUG)

---

## Support & Escalation

**Tier 1 (Operator)**: Health checks, log review, container restart
**Tier 2 (Technical Steward)**: Database queries, manual backfill, config updates
**Tier 3 (Developer)**: pytrends troubleshooting, schema migrations, stitching algorithm fixes

**Escalation Criteria**:
- Persistent `status=fail` for >3 days → Tier 2
- Database corruption → Tier 2
- pytrends library errors → Tier 3
- Stitching algorithm issues (>20% jumps) → Tier 3

**Documentation Links**:
- [plan.md](./plan.md): Technical architecture
- [research.md](./research.md): Technology decisions
- [data-model.md](./data-model.md): Database schema
- [contracts/database-schema.sql](./contracts/database-schema.sql): DDL reference

---

## Quick Reference Commands

```bash
# Start/Stop
docker compose up -d fetcher
docker compose stop fetcher
docker compose restart fetcher

# Health Check
curl http://localhost:8080/healthz | jq

# View Logs
docker compose logs -f fetcher --tail=50

# Manual Backfill
docker exec googili_fetcher python -m googili.fetcher backfill --days=14

# Database Query (Latest Batch)
docker exec googili_fetcher sqlite3 /app/data/googili.db \
  "SELECT * FROM events_raw_rsv_ingested ORDER BY finished_at_ict DESC LIMIT 1"

# Check Data Quality
docker exec googili_fetcher sqlite3 /app/data/googili.db \
  "SELECT * FROM v_data_quality"

# Force Archive Generation
docker exec googili_fetcher python -m googili.fetcher archive --month=2025-11

# Update Config
vi ~/googili/config/googili.toml
docker compose restart fetcher
```

---

## Glossary

- **RSV**: Relative Search Volume (0-100 scale from Google Trends)
- **Stitching**: Overlap-based scaling to create continuous time series
- **Batch Event**: Single ingestion run with provenance metadata
- **true_daily**: RSV from daily granularity request (high quality)
- **weekly_flat**: RSV derived from weekly data (coarse quality)
- **below_detection**: Missing data that cannot be retrieved even from weekly

---

**Status**: ✅ Complete and aligned with Googili constitution v1.1.0

**Last Updated**: 2025-11-04
**Next Review**: 2026-01-04 (quarterly per constitution)
