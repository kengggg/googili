# GOOGILI Data Directory

Centralized data storage for all GOOGILI modules (fetcher, analyser, visualiser).

## Structure

```
data/
├── raw/                    # Raw data from fetcher module
│   ├── rsv_trends.db      # SQLite database with Google Trends RSV data
│   └── archive/           # Monthly immutable CSV snapshots
├── processed/             # Processed data from analyser module
│   └── (future: metrics, anomalies, quality reports)
└── exports/               # Export artifacts from visualiser module
    └── (future: dashboards, reports, charts)
```

## Data Flow

```
Google Trends API
       ↓
   [fetcher]
       ↓
  data/raw/rsv_trends.db
       ↓
   [analyser]
       ↓
  data/processed/
       ↓
  [visualiser]
       ↓
  data/exports/
```

## Access Paths

### From fetcher/ directory:
- Database: `../data/raw/rsv_trends.db`
- Archive: `../data/raw/archive/`

### From analyser/ directory (future):
- Input: `../data/raw/rsv_trends.db`
- Output: `../data/processed/`

### From visualiser/ directory (future):
- Input: `../data/processed/`
- Output: `../data/exports/`

## Git Tracking

- Structure tracked via `.gitkeep` files
- Database files (*.db) ignored via `.gitignore`
- Archive CSVs ignored (except structure)

## DBeaver Connection

To query the database with DBeaver:
- **Type**: SQLite
- **Path**: `/Users/keng/Workspaces/mph/googili/data/raw/rsv_trends.db`
- **Auth**: None (leave empty)
