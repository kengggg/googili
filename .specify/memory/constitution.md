# GOOGILI Constitution

<!--
SYNC IMPACT REPORT
==================
Version change: 1.1.0 → 1.2.0
Change type: MINOR - Enhanced TDD principle with reality check and enforcement

Modified principles:
- **Principle III (TDD)**: Added comprehensive reality check documenting Phase 1 violation, remediation work, and strengthened enforcement

Added sections:
- TDD Reality Check (2025-11-05) - Documents historical violation, evidence, and remediation phases
- Key Learnings from Violation - 5 critical lessons learned from retrofit testing
- Behavioral Testing Principles - DO/DON'T guidelines with code examples
- Enforcement for Future Work - Code review checklist and violation policy

Modified sections:
- Principle III main text: Clarified "ALL TESTS MUST TEST BEHAVIORS NOT IMPLEMENTATION DETAILS"
- Testing Discipline: Strengthened with concrete examples of behavioral vs. implementation testing

Removed sections: None

Templates requiring updates:
✅ tasks-template.md - Already emphasizes TDD mandatory; now has constitutional backing with enforcement details
✅ plan-template.md - Constitution Check section compatible; TDD violations now documented
✅ checklist-template.md - Can add "Tests written before implementation" checklist item
⚠️ PR template - Should add TDD compliance checklist (tests validate behavior, no mock anti-patterns, test-first commits)

Impact on existing work:
- Fetcher Core (Phase 1): Violation documented, fully remediated with 186/186 passing behavioral tests
- Future phases (4-11): Must follow TRUE TDD with enforcement checklist
- All cores (Analyser, Visualiser): Must use behavioral testing principles from day one

Follow-up TODOs:
- Create PR template with TDD compliance checklist
- Add pre-commit hook to detect mock assertion anti-patterns (optional)
- Consider git commit-msg hook to require test commits before implementation commits (optional)

Version bump rationale: MINOR (1.2.0) - Materially expanded Principle III with historical context, lessons learned, behavioral testing guidelines, and enforcement mechanisms. This is substantive guidance that affects all future development practices.
-->

## Core Principles

### I. Adjunct Signal, Not Diagnostic

**The system provides early-warning signals for human review, never automated diagnosis.**

Google Trends RSV (Relative Search Volume, 0–100) is media-sensitive and represents digital access patterns, not disease prevalence. All outputs MUST be framed as cues requiring expert interpretation. Analytics MUST use conservative defaults to prevent over-alerting: `baseline_days=14`, `pct_threshold=0.60`, `debounce_hours=48`. UI and exports MUST prominently display caveats about uncertainty, media influence, and digital-access biases.

**Rationale**: Public health surveillance requires measured confidence intervals and expert judgment. Automation without human oversight risks misallocation of resources and potential stigmatization.

### II. Separation of Concerns (Three Cores)

**The architecture comprises three independent, bounded cores: Fetcher, Analyser, Visualiser.**

- **Fetcher**: Raw data ingestion from Google Trends; writes to SQLite; emits ingestion completion events.
- **Analyser**: Reads raw data; computes derived analytics (baseline, %Δ, alerts); writes results and analysis completion events.
- **Visualiser**: Read-only access to raw and derived data; presents dashboards, charts, and data-health widgets.

Each core MUST maintain strict boundaries: no direct function calls across cores; communication via database events and well-defined table contracts. NO GLOBAL VARIABLES AT ALL. Each core can be run independently without waiting for the other core. Breaking changes to shared schemas require explicit migration plans.

**Rationale**: Enables independent development, testing, and troubleshooting. Supports fail-safe operation where Visualiser remains usable with last good data when upstream fails.

### III. Test-Driven Development (NON-NEGOTIABLE)

**All code MUST be written using TDD: tests first, verify they fail, then implement, and verify all tests again. ALL TESTS MUST TEST BEHAVIORS NOT IMPLEMENTATION DETAILS. YOU ARE NOT ALLOWED TO SKIP THIS EVEN THOUGH THE PROCESS TAKES A LONG TIME. Using pytest.skip() TO MAKE THE TEST GREEN IS NOT ACCEPTABLE.**

- **Unit tests**: Stitching logic, percent-change calculations, debounce logic.
- **Contract tests**: Interface boundaries between Fetcher ↔ Analyser ↔ Visualiser.
- **Golden-file tests**: Time-series stitching with known overlaps and gaps.

Red-Green-Refactor cycle is mandatory. No implementation without failing tests first. All tests MUST be automated and pass before merging.

**Rationale**: Public health systems demand reliability. TDD ensures correctness, prevents regressions, and documents expected behavior.

#### TDD Reality Check (Added 2025-11-05)

**Historical Violation**: During initial Fetcher Core development (Tasks T001-T027), TDD was NOT followed. Tests were written AFTER implementation across 27 tasks, with 6 modules having ZERO test coverage initially. This violated Principle III completely.

**Evidence of Retrofit**:
- Implementation files existed without corresponding test files (db.py, config.py, logging_utils.py, keyword_config.py, db_operations.py)
- schema.sql (233 lines) existed before contract tests were written
- Tests referenced implementation internals they shouldn't know in true TDD (e.g., checking specific method calls, inspecting call arguments)
- Tests verified method existence rather than defining required behavior
- **Critical Bug Found**: scheduler.py missing config parameter for IngestionService—would have been prevented by TDD

**Remediation Completed (2025-11-05)**:

**Phase 1 - Add Missing Tests**: Created 113 comprehensive behavioral tests for modules with ZERO coverage
- test_database.py (20 tests) - Connection management, WAL mode, transactions
- test_config.py (26 tests) - TOML parsing, validation, province checks
- test_logging_utils.py (24 tests) - JSON formatting, Thai Unicode, structured logs
- test_keyword_config.py (27 tests) - Model validation, activation, serialization
- test_db_operations.py (16 tests) - UPSERT operations, batch events, record counting

**Phase 2 - Remove Mock Assertion Anti-patterns**: Refactored 37 existing tests to validate BEHAVIOR not implementation
- test_trends_fetcher.py - Removed mock call inspection, now verifies returned RSVRecord data
- test_scheduler.py - Removed call_kwargs checks, now verifies job execution completion
- test_cli.py - Removed call_args inspection, now verifies exit codes and service completion
- Eliminated: `.assert_called_once()`, `.assert_called_once_with()`, `.call_args`, `.call_kwargs`, `.call_count`

**Phase 3 - Fix Technical Issues**: Resolved 16 test failures (schema mismatches + timing incompatibilities)
- Fixed batch event schema mismatches (start_ict → started_at_ict, added required fields)
- Redesigned scheduler tests to use behavioral approach instead of freeze_time (incompatible with APScheduler threads)
- Created test_scheduler_behavioral.py with 11 new tests verifying WHAT scheduler does, not WHEN

**Results**:
- **Before Remediation**: 0% TDD compliance, 173 passing tests, 11 failing, 6 modules with zero coverage
- **After Remediation**: 186/186 tests passing (100%), comprehensive behavioral coverage, all mock anti-patterns removed
- **Test Quality**: All tests now validate observable outcomes (data, records, exit codes, database state) not implementation details

#### Key Learnings from Violation

1. **TDD Prevents Critical Bugs**: The scheduler.py config parameter bug was discovered during test creation. This bug would have caused runtime crashes. TRUE TDD would have prevented it entirely.

2. **Retrofit Tests Are Brittle**: Tests written after implementation break when code is safely refactored (method renames, parameter changes), even when behavior is unchanged. They test HOW code works, not WHAT it accomplishes.

3. **Mock Assertions Are Anti-patterns**: Checking `.assert_called_once_with()`, inspecting `.call_args`, or verifying `.call_kwargs` tests implementation details. These tests become worthless when implementation changes, even if behavior is identical.

4. **Implementation Knowledge Problem**: Retrofit tests "know" about private methods, internal attributes, and implementation choices because the implementation already exists. TRUE TDD tests only know the public contract and expected behavior.

5. **Constitution Matters**: "TDD is NON-NEGOTIABLE" must be PRACTICED, not just claimed. Declaring a principle without enforcement renders it meaningless.

#### Behavioral Testing Principles (Learned from Remediation)

**DO: Test Observable Outcomes**
- ✅ Verify returned data and records have correct values
- ✅ Check database state after operations
- ✅ Validate exit codes and error messages
- ✅ Test API contract compliance (correct fields, types, constraints)
- ✅ Verify logs contain required metadata

**DON'T: Test Implementation Details**
- ❌ `.assert_called_once()` - Don't count method calls
- ❌ `.assert_called_once_with()` - Don't verify exact parameters
- ❌ `.call_args` / `.call_kwargs` - Don't inspect call arguments
- ❌ `.call_count` - Don't count internal calls
- ❌ `hasattr()` checks - Don't verify method existence
- ❌ Testing private methods directly - Only test public contracts
- ❌ **Over-mocking** - Don't mock your own classes completely (use `@patch('main.MyClass')`)

**CRITICAL: The Over-Mocking Problem**

Mocking entire classes hides signature mismatches and parameter errors:

```python
# ❌ BAD: Complete mock hides signature errors
@patch('main.IngestionService')  # Mock accepts ANY arguments
def test_cli(mock_ingestion_class):
    mock_ingestion_class.return_value = Mock()
    # This passes even if real signature is wrong!
    IngestionService(db)  # Missing required 'config' parameter
```

**Result**: Tests pass, production crashes with `TypeError: missing required positional argument`

**Solution**: Use integration tests without mocking your own code:

```python
# ✅ GOOD: Integration test catches signature errors
def test_cli_integration():
    # Don't mock your own classes - test them!
    db = DatabaseConnection(':memory:')
    config = FetcherConfig()  # Forces correct signature
    ingestion = IngestionService(db, config)  # Would fail if signature wrong
```

**Examples**:

**BAD (Tests Implementation)**:
```python
# Anti-pattern: Tests HOW the code calls dependencies
mock_pytrends.build_payload.assert_called_once()
call_kwargs = mock_pytrends.build_payload.call_args[1]
assert call_kwargs['geo'] == 'TH-50'
```

**GOOD (Tests Behavior)**:
```python
# Behavioral: Tests WHAT the code returns
rsv_records = fetcher.fetch_daily('ไข้', date(2025, 11, 1))
assert rsv_records[0].province_code == 'TH-50'
assert rsv_records[0].keyword == 'ไข้'
```

#### Enforcement for Future Work (Phases 4-11)

**Before ANY implementation in future phases**:

1. **Write failing tests FIRST** - Every user story begins with RED tests
2. **Verify tests actually FAIL** - Run tests, confirm expected failures
3. **Implement MINIMAL code** to make tests pass (GREEN)
4. **Refactor** while keeping tests green
5. **Document test-first commits** - Tests and implementation committed together with test timestamp before implementation

**Code Review Checklist**:
- [ ] Tests written before implementation (verify git commit timestamps)
- [ ] Tests validate BEHAVIOR (data, exit codes, database state) not implementation (mock calls)
- [ ] Tests use behavioral assertions, no mock assertion anti-patterns
- [ ] Tests are resilient to refactoring (don't depend on internal methods/attributes)
- [ ] Tests document expected behavior through clear test names and assertions
- [ ] **Integration tests exist** for entry points (CLI, APIs) - NO mocking of your own classes
- [ ] **Critical paths tested end-to-end** - At least one integration test per user-facing feature

**Violations = Rejection**: Any PR without test-first evidence or containing mock assertion anti-patterns will be rejected, no exceptions.

**Commitment**: All future work (User Stories 2-6, Analyser Core, Visualiser Core) WILL follow TRUE TDD. The violation in Fetcher Core Phase 1 was identified, remediated, and will NOT be repeated.

#### Case Study: The Over-Mocking Bug (2025-11-05)

**Discovery**: After Phase 1-3 remediation achieving "186/186 tests passing (100%)", production CLI was found to be completely broken.

**Bug**: `main.py` called `IngestionService(db)` but signature requires `IngestionService(db, config)`
**Impact**: ALL CLI modes (--daily, --manual, --daemon, --backfill-initial) crash immediately with `TypeError`
**Tests**: ALL 12 CLI tests passed despite critical production bug
**Root Cause**: `@patch('main.IngestionService')` created mock accepting ANY arguments, hiding signature mismatch

**Why Tests Didn't Catch It**:
```python
@patch('main.IngestionService')  # Complete mock of our own class
def test_manual_ingestion(mock_ingestion_class):
    mock_ingestion_class.return_value = Mock()
    # This passes even though signature is wrong!
    run_manual('test.db', 'schema.sql', '2025-11-01')
```

**Lesson**: Over-mocking makes tests worthless. Mocks should be for **external dependencies** (Google Trends API), NOT for your own code (IngestionService).

**Fix Applied** (following TRUE TDD):
1. **RED**: Wrote failing integration test without mocking IngestionService
2. **GREEN**: Fixed `main.py` to pass `config` parameter
3. **VERIFY**: Integration test passes, production CLI works

**Prevention**: All entry points (CLI, APIs) MUST have at least one integration test with minimal mocking.

### IV. Data Governance & Provenance

**Every analysis run MUST record effective parameters, timestamps, and data lineage.**

- Each ingestion event stores: timestamp (Asia/Bangkok), keyword, date range, row count.
- Each analysis event stores: run timestamp, baseline_days used, pct_threshold, debounce_hours, number of alerts generated.
- Alerts include: keyword, date, RSV value, baseline value, %Δ, threshold used.
- Monthly archives (immutable snapshots) saved to `./archive` with small data dictionary.

No personal data is collected. Only aggregated RSV values. Compliance with platform (Google Trends) terms of use is mandatory.

**Rationale**: Reproducibility and auditability are essential for public health. Stakeholders must trace how alerts were generated and under what assumptions.

### V. Fail-Safe & Availability

**The Visualiser MUST remain operational with last good data when Fetcher or Analyser fails.**

- Visualiser queries database for most recent complete dataset.
- Data Health widget displays: last successful fetch timestamp, last successful analysis timestamp, detected anomalies (zero-rate runs, stitch gaps, integrity warnings).
- Status banners inform users when data is stale or degraded.
- `/healthz` endpoints per core report readiness (200 OK) or degraded (503 Service Unavailable).

**Rationale**: Surveillance continuity is critical. Operators must maintain situational awareness even during upstream failures.

### VI. Clarity Over Cleverness

**Use simple, explainable indicators and plain-language caveats.**

- **Baseline**: Mean RSV of recent `baseline_days` (default 14).
- **%Δ anomaly**: `((current_rsv - baseline) / baseline) * 100` when > `pct_threshold` (default 60%).
- **Debounce**: No new alert for same keyword within `debounce_hours` (default 48).

Avoid complex statistical models in MVP. Prioritize operator understanding and interpretability. All thresholds and assumptions MUST be visible in UI and configuration.

**Rationale**: Non-technical public health staff must understand and trust the system. Simplicity reduces misinterpretation and builds confidence.

### VII. Configuration-as-Code (Single File)

**All operational parameters MUST be defined in a single configuration file; no login or UI-based configuration in MVP.**

- Config file specifies: ~10 Thai keywords, province (Chiang Mai), baseline_days, pct_threshold, debounce_hours, archive cadence.
- Config changes are version-controlled.
- System reads config on startup and logs effective parameters.

**Rationale**: Operator-friendly; changes are auditable via git; no database-driven configuration complexity in MVP.

### VIII. Observability & Data Health

**System MUST surface data quality and operational health proactively.**

- **Data Health widget** in UI shows:
  - Last fetch timestamp, last analysis timestamp.
  - Zero-rate warnings (keywords returning all zeros).
  - Stitch overlap/gap integrity checks.
- **Logs**: Structured logging (JSON) for ingestion, analysis, and errors; retain for troubleshooting.
- **Healthz endpoints**: `/healthz` per core for monitoring/alerting integration.

**Rationale**: Early detection of data quality issues prevents false alerts and builds operator confidence.

### IX. Equity & Ethical Communication

**Acknowledge digital-access and media biases; avoid stigmatizing communities.**

- UI and exports MUST include disclaimers about digital-divide limitations and media-driven spikes.
- Avoid language that implies causality or certainty (e.g., "outbreak detected" → "search interest increased").
- Provide context about what RSV represents and what it does not.

**Rationale**: Search behavior reflects access and awareness, not disease burden. Misinterpretation can lead to inequitable resource allocation or stigmatization.

### X. User Experience & Accessibility

**The UI MUST be visually appealing, accessible, and fully functional on mobile devices.**

- **Good vibes**: Clean, modern design that reduces cognitive load; use whitespace effectively; maintain visual hierarchy.
- **Accessibility**: WCAG 2.2 AA compliance minimum; keyboard navigation; screen reader support; sufficient color contrast (4.5:1 for text).
- **Mobile-first**: Responsive design; touch targets ≥44×44px; readable on screens down to 320px width; optimize for field use.
- **Performance**: Fast load times on mobile networks (3G fallback); progressive enhancement; offline-capable where feasible (view last good data).

**Rationale**: Public health operators often work in field settings on mobile devices. Accessible, mobile-friendly design ensures usability across diverse contexts and user abilities, supporting equity and operational effectiveness.

## Public Health Ethics & Safety

**Do No Harm**. The system is an adjunct tool for expert review, never a replacement for routine surveillance (sentinel ILI, case reporting). Conservative defaults and prominent uncertainty caveats are mandatory.

**Transparency**. Assumptions, thresholds, and limitations MUST be visible in the UI, documentation, and help pages.

**Equity**. Recognize that search data reflects digital access and media coverage, which are unevenly distributed. Communicate limitations clearly to prevent misinterpretation or stigmatization.

## Engineering Practices & Quality

### SQLite with WAL (Write-Ahead Logging)

- Single database file for MVP.
- WAL mode for concurrency.
- Short-lived transactions; idempotent writes (upserts for ingestion, append-only for events).

### Database-Backed Events

- Append-only event tables signal ingestion and analysis completion.
- Cores poll or subscribe to events (no direct function calls).

### Testing Discipline

- **TDD mandatory** (Principle III).
- Unit tests for all logic: stitching, %Δ, debounce.
- Contract tests between cores (Fetcher output → Analyser input; Analyser output → Visualiser input).
- Golden-file tests for time-series stitching scenarios (overlaps, gaps).

### Performance Goals (MVP)

- **Timeliness**: Daily ingestion by 07:30 ICT; analysis within 1 hour post-fetch.
- **Performance**: Overview dashboard loads < 2 seconds for 90-day series; fetch+stitch per keyword < 60 seconds.
- **Availability**: Visualiser remains usable with last good data during upstream failures.

### Simplicity & Reversibility

- Ship small, reversible increments per core.
- Prefer simple solutions (YAGNI: You Aren't Gonna Need It).
- Migrations MUST be minimal and backward-compatible where possible.

## Governance

### Scope Management (MVP)

**In Scope**:
- Province: Chiang Mai (TH-50) only.
- ~10 Thai keywords via single config file.
- Daily and on-demand fetch.
- One-time 90-day backfill on first run.
- In-app alerts only; monthly archives saved to `./archive`.
- SQLite everywhere (raw, derived, events, metadata).

**Out of Scope (Deferred)**:
- Multi-province support.
- User accounts / authentication.
- Email, SMS, or LINE notifications.
- Integration with external surveillance systems.
- Advanced lead-lag evaluators or complex statistical models.

### Amendment Procedure

- Any change to **defaults** (`baseline_days`, `pct_threshold`, `debounce_hours`, archive cadence) MUST be reflected in the config file and documented in release notes.
- Constitution amendments require:
  1. Documented rationale for change.
  2. Impact assessment on existing deployments.
  3. Migration plan if breaking.
  4. Approval from project maintainers (or designated public health stakeholders).
- Version increments follow semantic versioning:
  - **MAJOR**: Backward-incompatible principle removals or redefinitions.
  - **MINOR**: New principles or materially expanded guidance.
  - **PATCH**: Clarifications, wording, typo fixes.

### Compliance & Review

- All pull requests MUST verify compliance with principles (checklist in PR template recommended).
- Complexity introduced counter to principles (e.g., sophisticated models, multi-core communication shortcuts) MUST be justified in writing and approved.
- Quarterly review of data quality and alert performance recommended (review thresholds, false-positive rates, operator feedback).

### Auditability

- Alerts and analyses carry parameters and timestamps.
- Monthly archives are immutable snapshots for reproducibility.
- Configuration changes are version-controlled.

### Documentation & Training

- **Help page** ("What it is / What it isn't") for end users.
- **Operator runbook** for cron setup, backfill procedure, and recovery from failures.
- Update documentation whenever principles or defaults change.

---

**Version**: 1.2.0 | **Ratified**: 2025-11-04 | **Last Amended**: 2025-11-05 | **Amendment**: Enhanced Principle III (TDD) with reality check, lessons learned, behavioral testing guidelines, and enforcement mechanisms following Phase 1-3 remediation work
