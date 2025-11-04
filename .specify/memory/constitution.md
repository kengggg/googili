# GOOGILI Constitution

<!--
SYNC IMPACT REPORT
==================
Version change: 1.0.0 → 1.1.0
Change type: MINOR - Added UI/UX principle

Modified principles:
- Added Principle X: User Experience & Accessibility (UI must look good, be accessible, support mobile)

Added sections:
- Core Principles (10 principles defined, was 9)
- Public Health Ethics & Safety
- Engineering Practices & Quality
- Governance

Removed sections: None

Templates requiring updates:
✅ plan-template.md - Constitution Check section already present and compatible
✅ spec-template.md - User scenarios align with public health ethics requirements
✅ tasks-template.md - TDD requirements align with Testing Discipline principle
✅ checklist-template.md - Compatible with constitution requirements; UI/UX can be added to checklist items
✅ agent-file-template.md - Compatible with constitution requirements

Follow-up TODOs:
- Consider creating a minimal help page template for MVP referenced in Principle X (Docs & training)
- Consider creating a minimal operator runbook template for MVP (cron, backfill, recovery procedures)

Version bump rationale: MINOR (1.1.0) - New principle added (UI/UX & Accessibility) expanding governance scope
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

Each core MUST maintain strict boundaries: no direct function calls across cores; communication via database events and well-defined table contracts. Each core can be run independently without waiting for the other core. Breaking changes to shared schemas require explicit migration plans.

**Rationale**: Enables independent development, testing, and troubleshooting. Supports fail-safe operation where Visualiser remains usable with last good data when upstream fails.

### III. Test-Driven Development (NON-NEGOTIABLE)

**All code MUST be written using TDD: tests first, verify they fail, then implement, and verify all tests again.**

- **Unit tests**: Stitching logic, percent-change calculations, debounce logic.
- **Contract tests**: Interface boundaries between Fetcher ↔ Analyser ↔ Visualiser.
- **Golden-file tests**: Time-series stitching with known overlaps and gaps.

Red-Green-Refactor cycle is mandatory. No implementation without failing tests first. All tests MUST be automated and pass before merging.

**Rationale**: Public health systems demand reliability. TDD ensures correctness, prevents regressions, and documents expected behavior.

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

**Version**: 1.1.0 | **Ratified**: 2025-11-04 | **Last Amended**: 2025-11-04
