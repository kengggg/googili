# Tasks: Fetcher Core - Google Trends RSV Data Ingestion

**Input**: Design documents from `/specs/001-fetcher-core/`
**Prerequisites**: plan.md, spec.md, data-model.md, research.md, contracts/database-schema.sql

**Tests**: ✅ **MANDATORY** - TDD is NON-NEGOTIABLE per Constitution Principle III. All tests MUST be written FIRST and FAIL before implementation.

**Organization**: Tasks grouped by user story to enable independent implementation and testing.

**Status**: Simplified per GitHub issue #4 - removed backfill, gap recovery, resampling; kept stitching for 'today 1-m' daily ingestion.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US3, US6)
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
- [X] T002 Initialize Python 3.12 project with requirements.txt (pytrends, pytest, python-json-logger, scipy)
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
- [X] T010 [P] Create example configuration file fetcher/config/googili.toml.example (10 Thai keywords, Thailand TH, schedule settings)
- [X] T011 [P] Implement timezone utilities in fetcher/src/lib/timezone_utils.py (Asia/Bangkok handling, ICT timestamp creation)
- [X] T012 Create base exception classes in fetcher/src/lib/exceptions.py (FetcherException, DatabaseException, ConfigException, PyTrendsException)

**Checkpoint**: Foundation ready - database schema applied, config loadable, logging functional. User story implementation can now begin in parallel.

---

## Phase 3: User Story 1 - Daily RSV Data with 'today 1-m' Ingestion (Priority: P1) 🎯 MVP

**Goal**: Reliable daily ingestion of Google Trends RSV for 10 Thai keywords using 'today 1-m' timeframe (~30 days per fetch), one keyword per request

**Independent Test**: Run daily ingestion, verify RSV data appears in database for all keywords with batch event metadata within 10 minutes

**Current Status**: ✅ IMPLEMENTED (simplified per GitHub issue #4) - uses `ingest()` method with 'today 1-m' timeframe, one keyword per request

### Tests for User Story 1 (TDD - WRITE FIRST, ENSURE FAIL) ⚠️

- [X] T013 [P] [US1] Unit test for pytrends wrapper in fetcher/tests/unit/test_trends_fetcher.py (mock pytrends responses, test error handling, rate limiting)
- [X] T014 [P] [US1] Unit test for batch event creation in fetcher/tests/unit/test_batch_event.py (validate batch_id generation, status transitions, metadata completeness)
- [X] T015 [P] [US1] Contract test for RSV record schema in fetcher/tests/contract/test_rsv_record_schema.py (verify all columns, constraints, foreign keys per database-schema.sql)
- [X] T016 [P] [US1] Contract test for batch event schema in fetcher/tests/contract/test_batch_event_schema.py (verify event structure matches spec.md requirements)
- [X] T017 [US1] Integration test for daily ingestion in fetcher/tests/integration/test_daily_ingestion.py (end-to-end: fetch → persist → verify batch event + RSV records)

### Implementation for User Story 1

- [X] T018 [P] [US1] Create RSV Record model in fetcher/src/models/rsv_record.py (keyword, date, rsv_raw, rsv_stitched, batch_id, granularity, quality attributes per data-model.md)
- [X] T019 [P] [US1] Create Batch Event model in fetcher/src/models/batch_event.py (batch_id, status, counts, timestamps, notes per data-model.md)
- [X] T020 [P] [US1] Create Keyword Configuration model in fetcher/src/models/keyword_config.py (term, active, province_code per data-model.md)
- [X] T021 [US1] Implement TrendsFetcher service in fetcher/src/services/trends_fetcher.py (pytrends wrapper, 'today 1-m' timeframe, TH scoping, rate limiting with 3-5s jitter per research.md)
- [X] T022 [US1] Implement database persistence layer in fetcher/src/lib/db_operations.py (UPSERT for RSV records, INSERT for batch events, idempotence enforcement)
- [X] T023 [US1] Implement Ingestion service in fetcher/src/services/ingestion.py (orchestrates fetch → [future: stitch] → persist → batch event emission, one keyword per request, error handling)
- [X] T024 [US1] Create simplified CLI entry point in fetcher/main.py (single command: `python main.py` runs ingestion, no daemon/scheduler modes)
- [X] T025 [US1] Add batch event logging to Ingestion service (structured JSON logs with batch_id, keywords, row counts per Constitution Principle VIII)

**Checkpoint**: Daily ingestion functional - can manually trigger fetches using 'today 1-m' timeframe, data persisted with batch events

---

## Phase 4: User Story 2 - Historical Context via 90-Day Backfill (Priority: P1) ❌ REMOVED

**Status**: ❌ **REMOVED per GitHub issue #4** - 'today 1-m' ingestion provides ~30 days rolling history, sufficient for operational surveillance

**Rationale**: The simplified approach uses 'today 1-m' timeframe which inherently provides recent history. 90-day backfill complexity was deemed unnecessary for MVP.

**Obsolete Tasks** (T028-T036):
- ~~T028-T030: Backfill tests~~
- ~~T031-T036: Backfill implementation~~

---

## Phase 5: User Story 3 - Continuous Time Series via Stitching (Priority: P1) 🎯 MVP - CURRENT WORK

**Goal**: Overlap-based stitching using trimmed mean to produce stable, continuous daily time series without normalization jumps

**Why Essential**: Daily 'today 1-m' fetches return INDEPENDENT 0-100 scales. Each fetch (~30 days) overlaps with previous fetch by ~29 days. Without stitching, this creates artificial level jumps. Stitching normalizes consecutive windows into a continuous time series.

**Independent Test**: Run multiple daily ingestions with overlapping windows, verify stitched RSV values show <20% jumps on stable days (SC-004)

**Current Status**: 🔄 **PLANNED** - Database schema ready (rsv_stitched column exists), configuration ready ([stitching] section exists), needs StitcherService implementation

### Tests for User Story 3 (TDD - WRITE FIRST, ENSURE FAIL) ⚠️

- [ ] T037 [P] [US3] Unit test for trimmed mean calculation in fetcher/tests/unit/test_stitcher.py (test 20% trim, outlier down-weighting, zero preservation per research.md Decision 2)
- [ ] T038 [P] [US3] Unit test for overlap window extraction in fetcher/tests/unit/test_stitcher.py (find overlap region between consecutive fetches, min 1-day validation)
- [ ] T039 [P] [US3] Golden-file test for stitching scenarios in fetcher/tests/golden/test_stitching_scenarios.py (load known overlap fixtures, verify <20% jumps, test edge cases: all-zeros, no overlap, outlier spikes)
- [ ] T040 [P] [US3] Unit test for stitching factor storage in fetcher/tests/unit/test_stitcher.py (verify scaling factor logged in batch event notes for audit)

### Implementation for User Story 3

- [ ] T041 [US3] Implement StitcherService class in fetcher/src/services/stitcher.py with find_overlap() method (queries database for existing records in overlap region for given keyword)
- [ ] T042 [US3] Implement compute_scaling_factor() method in StitcherService (scipy.stats.trim_mean with 20% proportiontocut per research.md, handles zero-division edge case)
- [ ] T043 [US3] Implement apply_stitching() method in StitcherService (applies scaling factor to new records, updates rsv_stitched attribute)
- [ ] T044 [US3] Integrate stitching into IngestionService.ingest() (after fetch, before persist: detect overlap → compute factor → apply stitching → update batch notes)
- [ ] T045 [US3] Add stitching metadata to batch events (store scaling factor, overlap size, stitching status in notes column for provenance)
- [ ] T046 [US3] Implement stitching degradation detection (warn if overlap <3 days, log integrity warning if no overlap found per spec edge case)
- [ ] T047 [US3] Add stitched value validation (verify no jumps >20% on consecutive days with stable behavior, alert if threshold exceeded)

**Checkpoint**: Stitching functional - consecutive fetches produce continuous time series without normalization artifacts

---

## Phase 6: User Story 4 - Gap Recovery After Outages (Priority: P2) ❌ REMOVED

**Status**: ❌ **REMOVED per GitHub issue #4** - Operators can manually re-run ingestion if needed. Automatic gap detection and 14-day rolling backfill are not implemented.

**Rationale**: Simplified implementation focuses on daily forward ingestion. Gap recovery complexity was deemed unnecessary for MVP.

**Obsolete Tasks** (T048-T056):
- ~~T048-T051: Gap detection tests~~
- ~~T052-T056: Recovery backfill implementation~~

---

## Phase 7: User Story 5 - Data Quality Transparency via Granularity Badges (Priority: P2) ❌ REMOVED

**Status**: ❌ **REMOVED per GitHub issue #4** - Weekly promotion and resampling policy are not implemented. All records have `granularity='daily'` and `quality='true'` (or NULL if below detection threshold).

**Rationale**: The 'today 1-m' approach consistently returns daily granularity. Resampling complexity was deemed unnecessary for MVP.

**Obsolete Tasks** (T057-T066):
- ~~T057-T060: Resampling tests~~
- ~~T061-T066: Resampling implementation~~

---

## Phase 8: User Story 6 - Provenance & Audit Trail for Governance (Priority: P3) ⚠️ PARTIAL

**Goal**: Complete provenance metadata in batch events, monthly archive snapshots with data dictionary

**Current Status**: ⚠️ **PARTIALLY IMPLEMENTED** - Batch events have full provenance metadata, but ArchiveService not yet implemented

**Independent Test**: Run multiple ingestion types (daily, manual), verify complete metadata in batch events, test monthly archive generation

### Tests for User Story 6 (TDD - WRITE FIRST, ENSURE FAIL) ⚠️

- [X] T067 [P] [US6] Contract test for batch event completeness in fetcher/tests/contract/test_event_schema.py (verify all FR-010 fields: batch_id, keywords, window, counts, status, timestamps, notes)
- [X] T068 [P] [US6] Unit test for batch_id generation in fetcher/tests/unit/test_batch_event.py (verify format "batch_YYYYMMDD_HHMMSS" in ICT timezone)
- [ ] T069 [P] [US6] Unit test for archive CSV generation in fetcher/tests/unit/test_archiver.py (verify columns, data dictionary content, month filtering)
- [ ] T070 [US6] Integration test for monthly archive in fetcher/tests/integration/test_archiver.py (trigger month-end archive, verify CSV files + README.txt created)

### Implementation for User Story 6

- [X] T071 [US6] Implement batch_id generator in BatchEvent model (format: batch_YYYYMMDD_HHMMSS using Asia/Bangkok timezone)
- [X] T072 [US6] Enhance batch event metadata in Ingestion service (populate requested_keywords as JSON array, requested_window as string, all count fields)
- [ ] T073 [US6] Implement Archiver service in fetcher/src/services/archiver.py (exports raw_trenddata, events_raw_rsv_ingested, config_keywords to CSV for specified month)
- [ ] T074 [US6] Create data dictionary template for archives (README.txt template with column descriptions, constraints, quality flags, constitution version reference)
- [ ] T075 [US6] Add archive scheduler to CLI main (monthly trigger at month-end, invokes Archiver for previous month) - DEFERRED (no scheduler in simplified implementation)
- [ ] T076 [US6] Add CLI archive command (--archive --month=YYYY-MM for manual archive generation)
- [ ] T077 [US6] Implement batch event lineage queries (helper functions to trace RSV records back to batch events via batch_id FK)

**Checkpoint**: Provenance complete - full audit trail available, monthly archives can be generated manually

---

## Phase 9: HTTP 429 Rate Limiting Handling (US1 Extension) ✅ COMPLETED

**Context**: Google Trends API returns HTTP 429 when rate limited. Implementation includes retry with exponential backoff per FR-013.

**TDD Order**: Following TRUE TDD - tests BEFORE implementation

- [X] T101 [RED] [US1] Write FAILING tests for RateLimitException class (tests/unit/test_rate_limit_exception.py)
- [X] T102 [GREEN] [US1] Implement RateLimitException in lib/exceptions.py
- [X] T103 [RED] [US1] Write FAILING tests for retry configuration parsing (tests/unit/test_config_rate_limiting.py)
- [X] T104 [GREEN] [US1] Add rate_limiting section to config/googili.toml with defaults
- [X] T105 [GREEN] [US1] Update lib/config.py FetcherConfig to parse rate_limiting configuration

**Checkpoint**: Rate limiting configuration complete

---

## Phase 10: Test Suite Fixes (URGENT - 70+ Broken Tests) ⚠️

**Context**: Test suite references deleted `ingest_daily(target_date)` method. Current implementation uses simplified `ingest()` method without parameters.

**Current Status**: 🔄 **IN PROGRESS** - Many tests need updating to reflect simplified implementation

### Test Fixes Required

- [ ] T113 [P] Fix test_daily_ingestion.py (49 calls to deleted `ingest_daily()` method - replace with `ingest()`)
- [ ] T114 [P] Fix test_end_to_end.py (6 calls to deleted method)
- [ ] T115 [P] Fix test_scheduler_behavioral.py (6 mocks of deleted method - remove scheduler tests or mark as obsolete)
- [ ] T116 [P] Rewrite test_cli.py for simplified CLI (remove tests for deleted run_manual(), run_daily(), run_daemon() functions)
- [ ] T117 [P] Update test_config.py (remove backfill property tests, keep stitching configuration tests)

### New Tests for Simplified Implementation

- [ ] T118 [US1] Create test_ingestion_simplified.py with tests for:
  - One keyword per request (verify loop through keywords individually)
  - 'today 1-m' timeframe usage (verify no date calculations)
  - Jitter between requests (verify _apply_jitter() called between keywords)
  - Batch type='ingestion' (verify correct batch event type)
  - Idempotent re-runs (verify UPSERT semantics)

**Checkpoint**: Test suite fully passing with 100% alignment to simplified implementation

---

## Phase 11: Configuration & Schema Fixes ⚠️

**Context**: Minor configuration and schema issues identified during simplification

### Required Fixes

- [ ] T119 Fix schema province constraint (support both 'TH' and 'TH-50' in CHECK constraint)
- [ ] T120 Add [rate_limiting] section to root config/googili.toml (currently only in example file)
- [ ] T121 Update schema comments to reflect simplified implementation (remove references to backfill/recovery batch types if obsolete)

**Checkpoint**: Configuration and schema aligned with current implementation

---

## Phase 12: Health Endpoint & Observability (Cross-Cutting) ⚠️ DEFERRED

**Purpose**: /healthz endpoint for Docker healthcheck and Visualiser polling, per Constitution Principle V & VIII

**Status**: ⚠️ **DEFERRED** - Not yet implemented in simplified version

### Tests for Health Endpoint (TDD - WRITE FIRST, ENSURE FAIL) ⚠️

- [ ] T078 [P] Unit test for health probe in fetcher/tests/unit/test_health.py (test DB writability check, view query, timeout handling)
- [ ] T079 [P] Contract test for /healthz JSON schema in fetcher/tests/contract/test_healthz_contract.py (verify response structure matches spec)
- [ ] T080 Integration test for health endpoint in fetcher/tests/integration/test_health_endpoint.py (test 200 OK success, 200 degraded >24h, 503 DB failure scenarios)

### Implementation for Health Endpoint

- [ ] T081 Implement health probe table operations in fetcher/src/lib/health_probe.py (insert probe records, test DB writability)
- [ ] T082 Implement Flask health endpoint in fetcher/src/lib/health.py (GET /healthz, queries v_latest_batch, returns JSON)
- [ ] T083 Add health endpoint to CLI main (run Flask app on port 8080 in separate thread)
- [ ] T084 Add health status logic (return 200 success if recent fetch, 200 degraded if >24h, 503 if DB error)
- [ ] T085 Add Docker healthcheck configuration in Dockerfile (HEALTHCHECK CMD curl)

**Checkpoint**: Health endpoint functional - Docker can monitor Fetcher, Visualiser can poll status

---

## Phase 13: Docker Deployment (Cross-Cutting) ⚠️ DEFERRED

**Purpose**: Containerized deployment with Docker Compose per research.md

**Status**: ⚠️ **DEFERRED** - Not yet needed for simplified manual execution

### Tests for Docker Deployment (Integration) ⚠️

- [ ] T086 Integration test for Docker build in fetcher/tests/integration/test_docker_build.py
- [ ] T087 Integration test for Docker Compose in fetcher/tests/integration/test_docker_compose.py

### Implementation for Docker Deployment

- [ ] T088 Create Dockerfile for fetcher
- [ ] T089 Create docker-compose.yml
- [ ] T090 Create .dockerignore
- [ ] T091 Add environment variable configuration support
- [ ] T092 Test Docker Compose deployment end-to-end

**Checkpoint**: Docker deployment ready - single-command startup operational

---

## Phase 14: Polish & Documentation (Final Phase)

**Purpose**: Code quality, documentation, final validation per Constitution

- [ ] T093 [P] Add comprehensive docstrings to all modules (models, services, lib, cli) following Google Python Style Guide
- [ ] T094 [P] Run code linting and formatting (black, flake8, mypy type checking)
- [ ] T095 [P] Update fetcher/README.md with full usage instructions (CLI commands, configuration reference)
- [ ] T096 [P] Create development setup guide in fetcher/docs/DEVELOPMENT.md (local setup, test execution, debugging)
- [ ] T097 Run quickstart.md validation end-to-end (follow all steps from scratch, verify outcomes match documentation)
- [ ] T098 [P] Add constitution compliance checklist to fetcher/docs/CONSTITUTION_COMPLIANCE.md (verify all 10 principles satisfied)
- [ ] T099 Performance testing (verify daily fetch <10 minutes for 10 keywords per SC-003)
- [ ] T100 Security review (verify no credentials logged, TOML config validation, SQL injection prevention)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - start immediately ✅ COMPLETE
- **Foundational (Phase 2)**: Depends on Setup → BLOCKS all user stories ✅ COMPLETE
- **User Story 1 (Phase 3)**: Depends on Foundational ✅ COMPLETE (simplified)
- **User Story 3 (Phase 5)**: Depends on Foundational 🔄 CURRENT WORK
- **Rate Limiting (Phase 9)**: Extends US1 ✅ COMPLETE
- **Test Fixes (Phase 10)**: Can proceed immediately 🔄 URGENT
- **Config/Schema Fixes (Phase 11)**: Can proceed immediately ⚠️ NEEDED
- **User Story 6 (Phase 8)**: Can proceed in parallel with US3 ⚠️ PARTIAL
- **Health Endpoint (Phase 12)**: Deferred ⚠️ FUTURE
- **Docker (Phase 13)**: Deferred ⚠️ FUTURE
- **Polish (Phase 14)**: Depends on all desired user stories complete ⚠️ FUTURE

### Removed Dependencies

- ❌ **User Story 2 (90-Day Backfill)**: REMOVED
- ❌ **User Story 4 (Gap Recovery)**: REMOVED
- ❌ **User Story 5 (Quality Badges/Resampling)**: REMOVED
- ❌ **APScheduler/Daemon Mode**: REMOVED

### Current Priority Order

1. **IMMEDIATE**: Phase 5 (US3 Stitching) - Core functionality for continuous time series
2. **URGENT**: Phase 10 (Test Suite Fixes) - Restore test coverage to 100%
3. **NEEDED**: Phase 11 (Config/Schema Fixes) - Align configuration with current state
4. **NICE TO HAVE**: Phase 8 (ArchiveService completion) - Enable monthly exports

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

## Implementation Strategy (Revised for Simplified Scope)

### MVP First (User Story 1 + 3 - Both P1)

1. ✅ Complete **Phase 1: Setup** (T001-T005)
2. ✅ Complete **Phase 2: Foundational** (T006-T012) - CRITICAL GATE
3. ✅ Complete **Phase 3: US1 - Daily Ingestion** (T013-T025) - Simplified 'today 1-m' implementation
4. ✅ Complete **Phase 9: Rate Limiting** (T101-T105) - US1 extension
5. 🔄 Complete **Phase 5: US3 - Stitching** (T037-T047) - CURRENT WORK
6. 🔄 Complete **Phase 10: Test Suite Fixes** (T113-T118) - URGENT
7. Complete **Phase 11: Config/Schema Fixes** (T119-T121)
8. **STOP and VALIDATE**: Test MVP independently, verify all success criteria SC-001 to SC-010
9. Deploy/demo MVP - basic ingestion + stitching functional

### Incremental Delivery Beyond MVP

1. **MVP deployed** (US1 + US3) → Foundation operational with continuous time series
2. Add **Health Endpoint** (Phase 12) → Enable monitoring
3. Add **Docker Deployment** (Phase 13) → Enable containerized deployment
4. Add **ArchiveService** (Phase 8) → Enable monthly exports
5. Polish & Documentation (Phase 14) → Production-ready

---

## Notes

- **[P] tasks** = different files, no dependencies, can parallelize
- **[Story] label** = maps to spec.md user stories for traceability
- **TDD mandatory** = write tests FIRST, ensure FAIL, then implement
- **Constitution compliance** = verify all 10 principles throughout
- **Timezone critical** = all timestamps Asia/Bangkok (ICT), verify in tests
- **Performance goals** = validate daily fetch <10 min for 10 keywords per SC-003
- **Success criteria** = verify SC-001 to SC-010 in final validation
- **Golden-file tests** = T039 uses known stitching scenarios, maintain fixtures in version control
- **Simplified scope** = Removed backfill/recovery/resampling per GitHub issue #4, focus on daily 'today 1-m' ingestion + stitching
