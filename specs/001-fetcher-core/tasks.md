# Tasks: Fetcher Core - Google Trends RSV Data Ingestion

**Input**: Design documents from `/specs/001-fetcher-core/`
**Prerequisites**: plan.md, spec.md, data-model.md, research.md, contracts/database-schema.sql

**Tests**: ✅ **MANDATORY** - TDD is NON-NEGOTIABLE per Constitution Principle III. All tests MUST be written FIRST and FAIL before implementation.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5, US6)
- Include exact file paths in descriptions

## Path Conventions

Per plan.md, single backend service structure:
- `fetcher/src/` - Application code
- `fetcher/tests/` - All tests (unit, integration, contract, golden)
- `fetcher/config/` - Configuration files
- `fetcher/` - Docker and deployment files

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic directory structure per plan.md

- [X] T001 Create project directory structure (fetcher/src/{models,services,cli,lib}, fetcher/tests/{unit,integration,contract,golden}, fetcher/config)
- [X] T002 Initialize Python 3.11 project with requirements.txt (pytrends, APScheduler, Flask, pytest, python-json-logger, scipy)
- [X] T003 [P] Create .gitignore for Python project (venv/, __pycache__/, *.pyc, data/, *.db)
- [X] T004 [P] Create fetcher/README.md with quick start instructions
- [X] T005 [P] Create fetcher/src/__init__.py as package marker

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story - database layer, config, logging per Constitution

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T006 Implement database connection module in fetcher/src/lib/db.py (SQLite with WAL mode, connection pooling, PRAGMA settings)
- [X] T007 [P] Implement TOML configuration loader in fetcher/src/lib/config.py (loads googili.toml, validates structure)
- [X] T008 [P] Implement structured JSON logger in fetcher/src/lib/logger.py (python-json-logger, batch metadata support)
- [X] T009 Apply database schema from contracts/database-schema.sql (create tables, indexes, views, triggers)
- [X] T010 [P] Create example configuration file fetcher/config/googili.toml.example (10 Thai keywords, Chiang Mai TH-50, schedule settings)
- [X] T011 [P] Implement timezone utilities in fetcher/src/lib/timezone_utils.py (Asia/Bangkok handling, ICT timestamp creation)
- [X] T012 Create base exception classes in fetcher/src/lib/exceptions.py (FetcherException, DatabaseException, ConfigException, PyTrendsException)

**Checkpoint**: Foundation ready - database schema applied, config loadable, logging functional. User story implementation can now begin in parallel.

---

## Phase 3: User Story 1 - Daily RSV Data Availability (Priority: P1) 🎯 MVP

**Goal**: Reliable daily ingestion of Google Trends RSV for 10 Thai keywords with scheduled execution at 07:30 ICT

**Independent Test**: Run daily ingestion, verify RSV data appears in database for all keywords with batch event metadata within 10 minutes

### Tests for User Story 1 (TDD - WRITE FIRST, ENSURE FAIL) ⚠️

- [X] T013 [P] [US1] Unit test for pytrends wrapper in fetcher/tests/unit/test_trends_fetcher.py (mock pytrends responses, test error handling, rate limiting)
- [X] T014 [P] [US1] Unit test for batch event creation in fetcher/tests/unit/test_batch_event.py (validate batch_id generation, status transitions, metadata completeness)
- [X] T015 [P] [US1] Contract test for RSV record schema in fetcher/tests/contract/test_rsv_record_schema.py (verify all columns, constraints, foreign keys per database-schema.sql)
- [X] T016 [P] [US1] Contract test for batch event schema in fetcher/tests/contract/test_batch_event_schema.py (verify event structure matches spec.md requirements)
- [X] T017 [US1] Integration test for daily ingestion in fetcher/tests/integration/test_daily_ingestion.py (end-to-end: fetch → persist → verify batch event + RSV records)

### Implementation for User Story 1

- [X] T018 [P] [US1] Create RSV Record model in fetcher/src/models/rsv_record.py (keyword, date, rsv_raw, batch_id, granularity, quality attributes per data-model.md)
- [X] T019 [P] [US1] Create Batch Event model in fetcher/src/models/batch_event.py (batch_id, status, counts, timestamps, notes per data-model.md)
- [X] T020 [P] [US1] Create Keyword Configuration model in fetcher/src/models/keyword_config.py (term, active, province_code per data-model.md)
- [X] T021 [US1] Implement TrendsFetcher service in fetcher/src/services/trends_fetcher.py (pytrends wrapper, daily/weekly granularity, TH-50 scoping, rate limiting with 3-5s jitter per research.md)
- [X] T022 [US1] Implement database persistence layer in fetcher/src/lib/db_operations.py (UPSERT for RSV records, INSERT for batch events, idempotence enforcement)
- [X] T023 [US1] Implement Ingestion service in fetcher/src/services/ingestion.py (orchestrates fetch → persist → batch event emission, error handling)
- [X] T024 [US1] Implement APScheduler configuration in fetcher/src/services/scheduler.py (07:30 ICT schedule, ±2 min jitter, graceful shutdown)
- [X] T025 [US1] Create CLI entry point in fetcher/main.py (supports --daily, --daemon, --manual, --backfill-initial modes)
- [X] T026 [US1] Add batch event logging to Ingestion service (structured JSON logs with batch_id, keywords, row counts per Constitution Principle VIII)
- [X] T027 [US1] Implement on-demand manual ingestion trigger in CLI (--manual flag, creates batch event marked "manual trigger")

**Checkpoint**: Daily ingestion functional - can schedule or manually trigger fetches, data persisted with batch events

---

## Phase 4: User Story 2 - Historical Context via 90-Day Backfill (Priority: P1) 🎯 MVP

**Goal**: Automatic 90-day historical backfill on first deployment to initialize time series

**Independent Test**: Start with empty database, verify system triggers 90-day backfill automatically, creates continuous time series for all keywords

### Tests for User Story 2 (TDD - WRITE FIRST, ENSURE FAIL) ⚠️

- [X] T028 [P] [US2] Unit test for backfill window calculation in fetcher/tests/unit/test_backfill_windowing.py (90-day range, date arithmetic in Asia/Bangkok timezone)
- [X] T029 [P] [US2] Behavioral tests for ingestion service in fetcher/tests/unit/test_ingestion_behavior.py (empty DB triggers backfill, populated DB runs daily, no duplicates, recovery scenarios - tests WHAT users see, not HOW code works)
- [X] T030 [US2] Integration test for 90-day backfill in fetcher/tests/integration/test_initial_backfill.py (clean DB → backfill → verify 90 days × 10 keywords = 900 records)

### Implementation for User Story 2

- [X] T031 [US2] Implement backfill window calculator in fetcher/src/services/backfill.py (computes 90-day date range, handles partial availability per spec edge case)
- [X] T032 [US2] Implement database state detector in fetcher/src/lib/db_state.py (checks if raw_trenddata empty, determines first-run vs. recovery)
- [X] T033 [US2] Add first-run backfill logic to Ingestion service (detects empty DB on startup, triggers 90-day backfill, marks batch event "initial backfill")
- [X] T034 [US2] Add CLI backfill command in fetcher/main.py (--backfill --days=90, supports manual backfill invocation)
- [X] T035 [US2] Implement batch chunking for backfill in BackfillService (avoid single massive request, chunk into weekly requests per pytrends best practices)
- [X] T036 [US2] Add backfill progress logging (log each chunk completion, total rows written, estimated time remaining)

**Checkpoint**: 90-day backfill works - empty database initializes with historical data automatically

---

## Phase 5: User Story 3 - Continuous Time Series via Stitching (Priority: P1) 🎯 MVP

**Goal**: Overlap-based stitching using trimmed mean to produce stable, continuous daily time series without normalization jumps

**Independent Test**: Run multiple daily ingestions with overlapping windows, verify stitched RSV values show <20% jumps on stable days (SC-004)

### Tests for User Story 3 (TDD - WRITE FIRST, ENSURE FAIL) ⚠️

- [ ] T037 [P] [US3] Unit test for trimmed mean calculation in fetcher/tests/unit/test_stitcher.py (test 20% trim, outlier down-weighting, zero preservation per research.md Decision 2)
- [ ] T038 [P] [US3] Unit test for overlap window extraction in fetcher/tests/unit/test_windowing.py (find overlap region between consecutive fetches, min 1-day validation)
- [ ] T039 [P] [US3] Golden-file test for stitching scenarios in fetcher/tests/golden/test_stitching_scenarios.py (load known overlap fixtures, verify <20% jumps, test edge cases: all-zeros, no overlap, outlier spikes)
- [ ] T040 [US3] Unit test for stitching factor storage in fetcher/tests/unit/test_stitcher.py (verify scaling factor logged in batch event notes for audit)

### Implementation for User Story 3

- [ ] T041 [US3] Implement overlap window calculator in fetcher/src/services/stitcher.py (identifies date range overlap between old and new windows)
- [ ] T042 [US3] Implement trimmed mean scaling factor calculation in Stitcher service (scipy.stats.trim_mean with 20% proportiontocut per research.md)
- [ ] T043 [US3] Implement RSV stitching application in Stitcher service (applies scaling factor, updates rsv_stitched column, handles zero-division edge case)
- [ ] T044 [US3] Integrate stitching into Ingestion service (fetch → detect overlap → compute factor → apply stitching → persist)
- [ ] T045 [US3] Add stitching metadata to batch events (store scaling factor, overlap size, stitching status in notes column for provenance)
- [ ] T046 [US3] Implement stitching degradation detection (warn if overlap <3 days, log integrity warning if no overlap found per spec edge case)
- [ ] T047 [US3] Add stitched value validation (verify no jumps >20% on consecutive days with stable behavior, alert if threshold exceeded)

**Checkpoint**: Stitching functional - consecutive fetches produce continuous time series without normalization artifacts

---

## Phase 6: User Story 4 - Gap Recovery After Outages (Priority: P2)

**Goal**: Automatic 14-day rolling backfill when ingestion offline >24 hours, no duplicates created

**Independent Test**: Simulate 3-day outage, restart system, verify 14-day backfill triggers automatically and fills gaps with zero duplicates (SC-005)

### Tests for User Story 4 (TDD - WRITE FIRST, ENSURE FAIL) ⚠️

- [ ] T048 [P] [US4] Unit test for gap detection in fetcher/tests/unit/test_gap_detector.py (compare last fetch timestamp to current time, detect >24h gap)
- [ ] T049 [P] [US4] Unit test for recovery window calculation in fetcher/tests/unit/test_backfill_windowing.py (14-day rolling window from last fetch)
- [ ] T050 [P] [US4] Unit test for UPSERT idempotence in fetcher/tests/unit/test_db_upsert.py (verify INSERT OR REPLACE on (keyword, date) prevents duplicates)
- [ ] T051 [US4] Integration test for recovery backfill in fetcher/tests/integration/test_recovery_backfill.py (simulate outage → restart → verify gap filled, zero duplicates)

### Implementation for User Story 4

- [ ] T052 [US4] Implement gap detector in fetcher/src/lib/gap_detector.py (queries v_latest_batch view, compares finished_at_ict to current time Asia/Bangkok)
- [ ] T053 [US4] Implement recovery backfill trigger in CLI main (on startup, check gap >24h, trigger 14-day backfill before starting scheduler)
- [ ] T054 [US4] Add recovery backfill mode to Backfill service (14-day window from last fetch, marks batch event "recovery backfill")
- [ ] T055 [US4] Enhance UPSERT logic in db_operations (ensure INSERT OR REPLACE on PRIMARY KEY (keyword, date), log overwrite events)
- [ ] T056 [US4] Add gap recovery logging (log gap size detected, recovery window calculated, rows updated vs. inserted)

**Checkpoint**: Recovery backfill works - system auto-heals after outages without manual intervention

---

## Phase 7: User Story 5 - Data Quality Transparency via Granularity Badges (Priority: P2)

**Goal**: Sparse-day 3-step fallback policy with explicit quality flags (true_daily, weekly_flat, below_detection)

**Independent Test**: Create scenario with missing daily data for 4-day run, verify weekly promotion, quality=coarse flags set correctly

### Tests for User Story 5 (TDD - WRITE FIRST, ENSURE FAIL) ⚠️

- [ ] T057 [P] [US5] Unit test for sparse-day detection in fetcher/tests/unit/test_resampler.py (identify ≥3 consecutive days missing daily data)
- [ ] T058 [P] [US5] Unit test for weekly promotion logic in fetcher/tests/unit/test_resampler.py (promote to weekly granularity, set impute_method='weekly_flat', quality='coarse')
- [ ] T059 [P] [US5] Unit test for quality flag exclusion in fetcher/tests/unit/test_stitcher.py (verify coarse records excluded from future stitching factor calculations per FR-011)
- [ ] T060 [US5] Integration test for resampling policy in fetcher/tests/integration/test_resampling.py (test full 3-step fallback: re-fetch → weekly → below_detection)

### Implementation for User Story 5

- [ ] T061 [US5] Implement Resampler service in fetcher/src/services/resampler.py (3-step fallback: Step 1 re-fetch wider window, Step 2 promote to weekly if ≥3-day run, Step 3 mark below_detection)
- [ ] T062 [US5] Add weekly granularity fetch to TrendsFetcher service (support granularity='weekly' parameter for pytrends)
- [ ] T063 [US5] Integrate resampling into Ingestion service (detect sparse days → invoke Resampler → persist with quality flags)
- [ ] T064 [US5] Implement quality flag filtering in Stitcher (exclude quality='coarse' records when computing future scaling factors per FR-011)
- [ ] T065 [US5] Add quality metrics to batch events (count true_daily, weekly_flat, missing per batch, populate batch event columns)
- [ ] T066 [US5] Add zero-rate warning detection (identify all-zeros for keyword across ≥3 days, log warning in batch event notes per spec edge case)

**Checkpoint**: Resampling policy functional - sparse days handled honestly with explicit quality badges

---

## Phase 8: User Story 6 - Provenance & Audit Trail for Governance (Priority: P3)

**Goal**: Complete provenance metadata in batch events, monthly archive snapshots with data dictionary

**Independent Test**: Run multiple ingestion types (daily, backfill, manual), verify complete metadata in batch events, test monthly archive generation

### Tests for User Story 6 (TDD - WRITE FIRST, ENSURE FAIL) ⚠️

- [ ] T067 [P] [US6] Contract test for batch event completeness in fetcher/tests/contract/test_event_schema.py (verify all FR-008 fields: batch_id, keywords, window, counts, status, timestamps, notes)
- [ ] T068 [P] [US6] Unit test for batch_id generation in fetcher/tests/unit/test_batch_event.py (verify format "batch_YYYYMMDD_HHMMSS" in ICT timezone)
- [ ] T069 [P] [US6] Unit test for archive CSV generation in fetcher/tests/unit/test_archiver.py (verify columns, data dictionary content, month filtering)
- [ ] T070 [US6] Integration test for monthly archive in fetcher/tests/integration/test_archiver.py (trigger month-end archive, verify CSV files + README.txt created)

### Implementation for User Story 6

- [ ] T071 [US6] Implement batch_id generator in BatchEvent model (format: batch_YYYYMMDD_HHMMSS using Asia/Bangkok timezone)
- [ ] T072 [US6] Enhance batch event metadata in Ingestion service (populate requested_keywords as JSON array, requested_window as string, all count fields)
- [ ] T073 [US6] Implement Archiver service in fetcher/src/services/archiver.py (exports raw_trenddata, events_raw_rsv_ingested, config_keywords to CSV for specified month)
- [ ] T074 [US6] Create data dictionary template for archives (README.txt template with column descriptions, constraints, quality flags, constitution version reference)
- [ ] T075 [US6] Add archive scheduler to CLI main (monthly trigger at month-end, invokes Archiver for previous month)
- [ ] T076 [US6] Add CLI archive command (--archive --month=YYYY-MM for manual archive generation)
- [ ] T077 [US6] Implement batch event lineage queries (helper functions to trace RSV records back to batch events via batch_id FK)

**Checkpoint**: Provenance complete - full audit trail available, monthly archives auto-generated

---

## Phase 9: Health Endpoint & Observability (Cross-Cutting)

**Purpose**: /healthz endpoint for Docker healthcheck and Visualiser polling, per Constitution Principle V & VIII

### Tests for Health Endpoint (TDD - WRITE FIRST, ENSURE FAIL) ⚠️

- [ ] T078 [P] Unit test for health probe in fetcher/tests/unit/test_health.py (test DB writability check, view query, timeout handling)
- [ ] T079 [P] Contract test for /healthz JSON schema in fetcher/tests/contract/test_healthz_contract.py (verify response structure matches spec: status, last_fetch, batch_id, row counts, db_writable)
- [ ] T080 Integration test for health endpoint in fetcher/tests/integration/test_health_endpoint.py (test 200 OK success, 200 degraded >24h, 503 DB failure scenarios)

### Implementation for Health Endpoint

- [ ] T081 Implement health probe table operations in fetcher/src/lib/health_probe.py (insert probe records, test DB writability per database-schema.sql trigger)
- [ ] T082 Implement Flask health endpoint in fetcher/src/lib/health.py (GET /healthz, queries v_latest_batch, returns JSON with status/timestamps/counts per research.md Decision 6)
- [ ] T083 Add health endpoint to CLI main (run Flask app on port 8080 in separate thread when --daemon mode)
- [ ] T084 Add health status logic (return 200 success if recent fetch, 200 degraded if >24h, 503 if DB error or query fails)
- [ ] T085 Add Docker healthcheck configuration in Dockerfile (HEALTHCHECK CMD curl -fsS http://localhost:8080/healthz per quickstart.md)

**Checkpoint**: Health endpoint functional - Docker can monitor Fetcher, Visualiser can poll status

---

## Phase 10: Docker Deployment (Cross-Cutting)

**Purpose**: Containerized deployment with Docker Compose per research.md Decision 9

### Tests for Docker Deployment (Integration) ⚠️

- [ ] T086 Integration test for Docker build in fetcher/tests/integration/test_docker_build.py (verify Dockerfile builds successfully, image tagged correctly)
- [ ] T087 Integration test for Docker Compose in fetcher/tests/integration/test_docker_compose.py (docker compose up succeeds, healthcheck passes, volumes mounted)

### Implementation for Docker Deployment

- [ ] T088 Create Dockerfile for fetcher (Python 3.11-slim base, copy src/, install requirements.txt, ENTRYPOINT python -m fetcher.cli.main)
- [ ] T089 Create docker-compose.yml (service definition with TZ=Asia/Bangkok, volume mounts for data/ and config/, port 8080 exposed, healthcheck, restart unless-stopped per quickstart.md Step 3)
- [ ] T090 Create .dockerignore (exclude tests/, venv/, __pycache__/, *.pyc, data/, *.db)
- [ ] T091 Add environment variable configuration support (LOG_LEVEL, DB_PATH overrides via ENV)
- [ ] T092 Test Docker Compose deployment end-to-end (docker compose up -d → verify healthcheck passes → trigger ingestion → verify data persists)

**Checkpoint**: Docker deployment ready - single-command startup operational

---

## Phase 11: Polish & Documentation (Final Phase)

**Purpose**: Code quality, documentation, final validation per Constitution

- [ ] T093 [P] Add comprehensive docstrings to all modules (models, services, lib, cli) following Google Python Style Guide
- [ ] T094 [P] Run code linting and formatting (black, flake8, mypy type checking)
- [ ] T095 [P] Update fetcher/README.md with full usage instructions (CLI commands, Docker deployment, configuration reference)
- [ ] T096 [P] Create development setup guide in fetcher/docs/DEVELOPMENT.md (local setup without Docker, test execution, debugging)
- [ ] T097 Run quickstart.md validation end-to-end (follow all steps from scratch, verify outcomes match documentation)
- [ ] T098 [P] Add constitution compliance checklist to fetcher/docs/CONSTITUTION_COMPLIANCE.md (verify all 10 principles satisfied with evidence)
- [ ] T099 Performance testing (verify 90-day backfill <15 min for 10 keywords per SC-003, daily fetch <60s per performance goals)
- [ ] T100 Security review (verify no credentials logged, TOML config validation, SQL injection prevention via parameterized queries)

### HTTP 429 Rate Limiting Handling (FR-016)

**Context**: Google Trends API returns HTTP 429 when rate limited. Current implementation treats this as fatal error, causing permanent data gaps. Must implement retry with exponential backoff per FR-016.

**TDD Order**: Following TRUE TDD - tests BEFORE implementation

- [X] T101 [RED] [US1] Write FAILING tests for RateLimitException class (tests/unit/test_rate_limit_exception.py) - verify inheritance from PyTrendsException, retry_after attribute storage, serialization for logging
- [X] T102 [GREEN] [US1] Implement RateLimitException in lib/exceptions.py (minimal code to pass T101 tests)
- [X] T103 [RED] [US1] Write FAILING tests for retry configuration parsing (tests/unit/test_config_rate_limiting.py) - verify default values, TOML parsing, validation
- [X] T104 [GREEN] [US1] Add rate_limiting section to config/googili.toml with defaults (max_retries=3, backoff_base_seconds=60, backoff_multiplier=5.0, max_backoff_seconds=1800, respect_retry_after=true)
- [X] T105 [GREEN] [US1] Update lib/config.py FetcherConfig to parse rate_limiting configuration with validation
- [ ] T106 [RED] [US1] Write FAILING tests for exponential backoff retry logic (tests/unit/test_trends_fetcher_retry.py) - verify retry on 429, backoff calculation, Retry-After header respect, RateLimitException after max retries, jitter randomization
- [ ] T107 [GREEN] [US1] Implement exponential backoff retry in services/trends_fetcher.py fetch_daily_rsv() and fetch_weekly_rsv() methods - wrap pytrends calls in retry loop, catch TooManyRequestsError, calculate backoff with jitter, log retry attempts
- [ ] T108 [RED] [US1] Write FAILING tests for ingestion RateLimitException handling (tests/unit/test_ingestion_rate_limiting.py) - verify batch marked "degraded" not "fail" on RateLimitException, other PyTrendsException still fail
- [ ] T109 [GREEN] [US1] Update services/ingestion.py ingest_daily() to catch RateLimitException separately, mark batch degraded with notes, don't re-raise (allow graceful degradation)
- [ ] T110 [RED] [US2] Write FAILING integration tests for backfill per-date retry (tests/integration/test_cli_backfill_retry.py) - verify failed dates retried after cooldown, batch continues after 429 (not aborted), exit code based on final success
- [ ] T111 [GREEN] [US2] Rewrite main.py run_backfill_initial() to implement per-date retry loop - collect failed dates, retry after cooldown, provide detailed progress logging
- [ ] T112 [GREEN] [US1] Add 429 guidance to main.py run_manual() - catch RateLimitException, display helpful retry command with suggested wait time

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - start immediately
- **Foundational (Phase 2)**: Depends on Setup → BLOCKS all user stories
- **User Stories (Phases 3-8)**: All depend on Foundational completion
  - US1, US2, US3 (P1) can proceed in parallel after Foundational
  - US4, US5 (P2) can proceed in parallel but integrate with P1 stories
  - US6 (P3) can proceed but references all prior stories
- **Health Endpoint (Phase 9)**: Can start after Foundational, integrates with US1 batch events
- **Docker (Phase 10)**: Can start after US1 complete (needs basic ingestion working)
- **Polish (Phase 11)**: Depends on all desired user stories complete

### User Story Dependencies

- **User Story 1 (P1 - Daily Ingestion)**: Foundation only - **MVP CORE**
- **User Story 2 (P1 - 90-Day Backfill)**: Foundation only, extends US1 - **MVP CORE**
- **User Story 3 (P1 - Stitching)**: Foundation only, extends US1 - **MVP CORE**
- **User Story 4 (P2 - Gap Recovery)**: Depends on US1, US2 (uses backfill + ingestion)
- **User Story 5 (P2 - Quality Badges)**: Depends on US1, US3 (uses ingestion + stitching)
- **User Story 6 (P3 - Provenance)**: Extends US1 batch events, can be deferred post-MVP

### Within Each User Story (TDD - NON-NEGOTIABLE)

1. **Tests FIRST** - write all tests, ensure they FAIL
2. Models - domain entities
3. Services - business logic
4. Integration - wire services together
5. Verify tests PASS - all tests must pass before story complete

### Parallel Opportunities

- **Phase 1 Setup**: All tasks with [P] can run in parallel
- **Phase 2 Foundational**: T007 config + T008 logger + T011 timezone + T012 exceptions can run parallel after T006 database
- **Once Foundational completes**:
  - US1, US2, US3 (all P1) can start in parallel (different services/models)
  - US4, US5 (both P2) can start in parallel after P1 stories
- **Within each story**: All tests marked [P] can run parallel, all models marked [P] can run parallel

---

## Parallel Example: User Story 1

```bash
# Write all US1 tests in parallel (TDD - FAIL first):
Task T013: "Unit test for pytrends wrapper in fetcher/tests/unit/test_trends_fetcher.py"
Task T014: "Unit test for batch event creation in fetcher/tests/unit/test_batch_event.py"
Task T015: "Contract test for RSV record schema in fetcher/tests/contract/test_rsv_record_schema.py"
Task T016: "Contract test for batch event schema in fetcher/tests/contract/test_batch_event_schema.py"

# Create all US1 models in parallel (after tests written):
Task T018: "Create RSV Record model in fetcher/src/models/rsv_record.py"
Task T019: "Create Batch Event model in fetcher/src/models/batch_event.py"
Task T020: "Create Keyword Configuration model in fetcher/src/models/keyword_config.py"
```

---

## Parallel Example: User Story 3

```bash
# Write all US3 tests in parallel (TDD - FAIL first):
Task T037: "Unit test for trimmed mean calculation in fetcher/tests/unit/test_stitcher.py"
Task T038: "Unit test for overlap window extraction in fetcher/tests/unit/test_windowing.py"
Task T040: "Unit test for stitching factor storage in fetcher/tests/unit/test_stitcher.py"
```

---

## Implementation Strategy

### MVP First (User Stories 1, 2, 3 - All P1)

1. Complete **Phase 1: Setup** (T001-T005)
2. Complete **Phase 2: Foundational** (T006-T012) - CRITICAL GATE
3. Complete **Phase 3: US1 - Daily Ingestion** (T013-T027) - TDD: tests first → fail → implement → pass
4. Complete **Phase 4: US2 - 90-Day Backfill** (T028-T036) - TDD: tests first → fail → implement → pass
5. Complete **Phase 5: US3 - Stitching** (T037-T047) - TDD: tests first → fail → implement → pass
6. Complete **Phase 9: Health Endpoint** (T078-T085) - needed for Docker healthcheck
7. Complete **Phase 10: Docker** (T086-T092) - containerize for deployment
8. **STOP and VALIDATE**: Test MVP independently per quickstart.md, verify all success criteria SC-001 to SC-004
9. Deploy/demo MVP - basic ingestion + backfill + stitching functional

### Incremental Delivery Beyond MVP

1. **MVP deployed** (US1 + US2 + US3) → Foundation operational
2. Add **US4: Gap Recovery** (P2) → Test independently → Deploy (auto-healing added)
3. Add **US5: Quality Badges** (P2) → Test independently → Deploy (data transparency added)
4. Add **US6: Provenance** (P3) → Test independently → Deploy (full audit trail)
5. Each story adds value without breaking previous functionality

### Parallel Team Strategy

With multiple developers after Foundational complete:

1. **Developer A**: US1 (Daily Ingestion) - blocking for others
2. **Developer B**: US2 (Backfill) - can start parallel to A
3. **Developer C**: US3 (Stitching) - can start parallel to A
4. Once US1 done: **Developer A** → Health Endpoint + Docker
5. Once US1, US2 done: **Developer B** → US4 (Gap Recovery)
6. Once US1, US3 done: **Developer C** → US5 (Quality Badges)
7. Final: **Developer A or B or C** → US6 (Provenance)

---

## TDD Workflow Reminder (Constitution Principle III - NON-NEGOTIABLE)

For EVERY user story:

1. **RED**: Write all tests for the story, run tests → ALL MUST FAIL
2. **GREEN**: Implement minimal code to make tests pass
3. **REFACTOR**: Clean up code while keeping tests green
4. **VERIFY**: All tests pass before marking story complete
5. **COMMIT**: Commit passing tests + implementation together

**No exceptions**. TDD is mandatory per constitution.

---

## Notes

- **[P] tasks** = different files, no dependencies, can parallelize
- **[Story] label** = maps to spec.md user stories for traceability
- **TDD mandatory** = write tests FIRST, ensure FAIL, then implement
- **Each story independently testable** = can deploy/demo any P1 story alone
- **Constitution compliance** = verify all 10 principles throughout (checklist in T098)
- **Timezone critical** = all timestamps Asia/Bangkok (ICT), verify in tests
- **Performance goals** = validate in T099 (backfill <15min, fetch <60s, /healthz <100ms)
- **Success criteria** = verify SC-001 to SC-010 in final validation (quickstart.md T097)
- **Golden-file tests** = T039 uses known stitching scenarios, maintain fixtures in version control
- **Avoid**: Starting implementation before tests written, mixing user story code that breaks independence
