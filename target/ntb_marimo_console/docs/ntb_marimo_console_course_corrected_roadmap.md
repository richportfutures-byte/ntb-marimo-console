# NTB Marimo Console Course-Corrected Roadmap

## Status Basis

Current checkpoint: `1561904 Define R14 cockpit view model contract`.

Current state: R03 through R13 are fixture-safe and repository-verified as foundation checkpoints. R14 readiness audit and the R14 cockpit view-model contract are now committed, but the app is not yet a production-proven live workstation. The release candidate remains conditional, not live-proven.

Known unproven items:

- No real five-contract Schwab live session validation.
- No real CHART_FUTURES delivery proof across ES, NQ, CL, 6E, and MGC.
- No real symbol entitlement or rollover proof.
- No live DXY/yield proxy proof for 6E/MGC.
- No full RTH session stability proof.
- No confirmed operator-cockpit usability under live-session pressure.

## Course Correction

The prior roadmap was directionally correct but too linear and audit-prone. It placed Operator Workspace Redesign after many deep infrastructure phases, which preserved safety but delayed the central product question:

> Can an experienced futures trader launch the app during RTH and determine, within seconds, what the plan is, what is live, what is blocked, why it is blocked, and whether the preserved pipeline can be queried?

The corrected roadmap now prioritizes a usable cockpit vertical slice before additional broad foundation work. Further audits are allowed only when they protect correctness, prevent unsafe/fake wiring, or unblock a concrete implementation path.

## Non-Negotiable Product Boundaries

These boundaries remain unchanged:

- Final target contracts: ES, NQ, CL, 6E, MGC.
- Excluded final target contracts: ZN, GC.
- MGC is Micro Gold and must not be described, mapped, or implemented as GC.
- ZN must not be re-promoted into final target support.
- The preserved engine remains the sole decision authority.
- Live data may arm, block, invalidate, or annotate a query, but may not approve trades.
- Execution remains manual-only.
- No broker/order/execution/account/fill/P&L behavior.
- Default launch remains non-live.
- Live behavior remains explicitly opt-in.
- Fixture-safe default tests remain credential-free.
- No fixture fallback after live failure.
- No repeated Schwab login per Marimo refresh.
- No secrets, tokens, auth headers, streamer URLs, customer IDs, correl IDs, account IDs, or authorization payloads printed.
- Stale, missing, unsupported, lockout, invalidated, non-provenance, or display-derived states must never produce QUERY_READY.

## Revised Execution Strategy

The project should now move through five convergence bands rather than another long abstract phase sequence.

1. Cockpit convergence.
2. Data-path proof.
3. Contract completion.
4. Live rehearsal.
5. Release hardening.

The immediate objective is not polish. It is operational truth on one screen.

---

# Band A: Cockpit Convergence

## A1. R14 Readiness Audit, Narrow Only

Status: completed in `b37f487 Audit R14 operator workspace readiness`.

Purpose: Decide whether the current surfaces can support the R14 cockpit without loosening R12/R13 safety.

Scope:

- Inspect operator workspace models/builders.
- Inspect Marimo phase 1 renderer surfaces.
- Inspect session header/readiness summary.
- Inspect decision review surface.
- Inspect audit/replay surface.
- Inspect trigger transition log surface.
- Inspect lifecycle/session-state propagation.
- Inspect pipeline query gate wiring.

Output:

- A short readiness document or focused regression test only if needed.
- Explicit decision: R14 implementation justified, premature, or blocked.

Do not:

- Redesign the UI yet.
- Add new live behavior.
- Add new trading logic.
- Add broad defensive documentation unless it prevents unsafe wiring.

Acceptance:

- Current operator-surface gaps are identified.
- Query-gate provenance remains protected.
- Display/view-model/evaluation objects cannot enable query readiness.
- Working tree commits clean if changes are made.

Suggested prompt:

`PROMPT 065 - Audit R14 Operator Workspace Redesign Readiness`

Expected commit:

`Audit R14 operator workspace readiness`

## A2. R14 Cockpit Acceptance Contract

Status: completed in `1561904 Define R14 cockpit view model contract`.

Purpose: Convert the R14 UI goal into a concrete, testable view-model contract before layout work.

Required cockpit data model:

- Current profile.
- Contract.
- Contract support status.
- Runtime profile status.
- Stream/provider status or fixture-safe equivalent.
- Quote freshness or fixture-safe equivalent.
- Session clock/state.
- Event lockout state.
- Premarket brief status.
- Active setup count.
- Trigger state summaries.
- Distance-to-trigger fields where available.
- Required fields.
- Missing fields.
- Blocking reasons.
- QUERY_READY provenance.
- Pipeline gate state.
- Query enabled/disabled reason.
- Last pipeline result.
- Stage termination reason.
- NO_TRADE/APPROVED/REJECTED summary.
- Audit/replay availability.
- Trigger transition log availability.
- Operator note availability.

Acceptance:

- Primary cockpit can be rendered without raw JSON.
- Every disabled state has a text reason.
- No color-only communication.
- No confidence/progress sentiment bar.
- No cross-contract best-trade ranking.
- No alert language implying the trader should take a trade.
- No market logic is added in the UI layer.

Suggested prompt:

`PROMPT 066 - Define R14 Cockpit View Model Contract`

Expected commit:

`Define R14 cockpit view model contract`

## A3. R14 Primary Cockpit Shell

Purpose: Build the first usable operator cockpit shell from existing state, without adding new decision logic.

Layout:

Header:

- Profile.
- Contract.
- Support matrix state.
- Provider/stream state.
- Quote freshness.
- Session/event state.
- Gate summary.

Left panel: Premarket Plan

- Structural setups.
- Global guidance.
- Warnings.
- Invalidators.
- Trigger definitions.
- Fields used.

Center panel: Live Thesis Monitor

- Setup state cards.
- Trigger state.
- Distance to trigger.
- Current live/fixture values.
- Required/missing fields.
- Invalidators.
- Armed/query-ready status.

Right panel: Pipeline Gate

- Gate status.
- Query button or disabled equivalent.
- Query reason.
- Last pipeline result.
- Stage termination.
- Final decision summary.

Bottom panel: Evidence and Replay

- Run history.
- Audit replay.
- Session evidence.
- Operator notes.
- Trigger transition log.

Acceptance:

- Trader can identify readiness within 10 seconds.
- Trader can identify why blocked within 10 seconds.
- Each contract has an explicit current state.
- Debug/raw JSON surfaces are secondary.
- Fixture-safe behavior remains intact.

Suggested prompt:

`PROMPT 067 - Build R14 Primary Operator Cockpit Shell`

Expected commit:

`Build R14 operator cockpit shell`

## A4. R14 Blocked-State Usability Pass

Purpose: Make blocked states operationally useful rather than technically correct but visually buried.

Required blocked-state categories:

- Unsupported contract.
- Excluded contract.
- Missing runtime profile.
- Premarket brief not READY.
- Missing required live field.
- Stale quote.
- Missing chart bars.
- Event lockout.
- Trigger invalidated.
- Stream disabled.
- Stream error.
- Fixture mode.
- No produced TriggerStateResult provenance.
- No pipeline result yet.

Acceptance:

- Every block category is displayed as plain text.
- Each block category has a stable test fixture or regression.
- The cockpit distinguishes blocked, stale, lockout, unavailable, invalidated, and query-ready.
- The UI does not imply a blocked state is a trade signal.

Suggested prompt:

`PROMPT 068 - Surface Operator-Readable Blocked States`

Expected commit:

`Surface operator blocked-state reasons`

---

# Band B: Data-Path Proof

## B1. Five-Contract Stream Capability Audit

Purpose: Determine what is actually implemented versus assumed for live Schwab data across all final contracts.

Scope:

- Existing stream manager foundation.
- Stream cache behavior.
- Level One futures normalization.
- Chart futures normalization or absence.
- Symbol configuration.
- Rollover assumptions.
- Entitlement failure behavior.
- Refresh/cache behavior.
- Redaction.

Acceptance:

- Exact current support is documented for ES, NQ, CL, 6E, MGC.
- No live credentials are required.
- No secret paths are inspected.
- Gaps are mapped to implementation tasks.
- No implementation unless a narrow regression is required.

Suggested prompt:

`PROMPT 069 - Audit Five-Contract Schwab Stream Capability`

Expected commit:

`Audit five-contract Schwab stream capability`

## B2. CHART_FUTURES Delivery Contract

Purpose: Stop treating chart bars as conceptually available until the repo has a tested contract for them.

Required outputs:

- One-minute bar structure.
- Completed versus building bar distinction.
- Five-minute aggregation contract.
- Bar timestamp handling.
- Missing/partial/stale bar blocking behavior.
- Acceptance/rejection predicate inputs.

Acceptance:

- Partial bars are never treated as completed confirmation.
- Missing bars block trigger predicates requiring bars.
- Fixture tests prove 1m to 5m aggregation.
- No footprint, DOM, sweep, or aggressive order-flow inference is invented.

Suggested prompt:

`PROMPT 070 - Implement CHART_FUTURES Bar Contract and Blocking Semantics`

Expected commit:

`Add chart futures bar contract`

## B3. Live Observable Snapshot Coverage Completion

Purpose: Ensure the cockpit and trigger gate consume a consistent five-contract observable snapshot.

Required coverage:

- ES quote/bar freshness.
- NQ quote/bar freshness plus ES-relative dependency readiness.
- CL quote/bar freshness plus EIA lockout availability.
- 6E quote/bar freshness plus DXY/session dependency readiness.
- MGC quote/bar freshness plus DXY/yield dependency readiness.
- Provider status.
- Symbol match.
- Required fields present.
- Blocking reasons.

Acceptance:

- Snapshot serializes cleanly.
- Missing required fields block trigger readiness.
- Derived fields are labeled as derived.
- Unavailable fields are explicit, not inferred.
- Cockpit can render the snapshot without raw JSON.

Suggested prompt:

`PROMPT 071 - Complete Five-Contract Live Observable Snapshot Coverage`

Expected commit:

`Complete five-contract observable coverage`

---

# Band C: Contract Completion

## C1. ES Live Thesis Vertical Slice

Purpose: Prove the full loop on the simplest supported contract before completing all profiles.

Required loop:

- Load ES premarket plan.
- Read ES live/fixture observable snapshot.
- Evaluate ES trigger state.
- Render ES cockpit state.
- Enable query only on produced QUERY_READY provenance.
- Run preserved pipeline manually.
- Render last result and audit/replay availability.

Acceptance:

- ES works without ZN dependency.
- Stale/missing data blocks ES.
- Query gate remains manual.
- NO_TRADE remains a valid terminal result.
- No alternate trade suggestions after NO_TRADE.

Suggested prompt:

`PROMPT 072 - Prove ES Live Thesis Cockpit Vertical Slice`

Expected commit:

`Prove ES live thesis cockpit slice`

## C2. CL Live Thesis Vertical Slice

Purpose: Prove event/volatility blocking on the most safety-sensitive supported contract.

Required loop:

- Load CL premarket plan.
- Read CL quote/bar observable snapshot.
- Surface EIA lockout state.
- Surface post-EIA settling state if present.
- Evaluate volume/range prerequisites.
- Block clearly when volatility or required fields are missing.

Acceptance:

- CL blocks during EIA lockout.
- CL blocks when volatility/range prerequisites are missing.
- CL does not use DOM/sweep language unless sourced.
- Audit records include EIA status when query is submitted.

Suggested prompt:

`PROMPT 073 - Prove CL Live Thesis Cockpit Slice`

Expected commit:

`Prove CL live thesis cockpit slice`

## C3. NQ Runtime/Profile Onboarding

Purpose: Promote NQ from engine-supported but app-incomplete to cockpit-visible supported.

Required:

- `preserved_nq_phase1` runtime profile.
- NQ fixture artifacts.
- NQ premarket/watchman fixture.
- NQ live observable fixture.
- ES-relative strength dependency.
- Missing ES dependency blocks NQ.
- Explicit anchor for relative strength.

Acceptance:

- NQ cannot arm without ES data.
- NQ cannot arm without relative-strength anchor.
- Absolute NQ breakout alone is insufficient.
- NQ uses preserved engine path.

Suggested prompt:

`PROMPT 074 - Onboard NQ Runtime Profile and Relative-Strength Gate`

Expected commit:

`Onboard NQ runtime profile`

## C4. 6E Runtime/Profile Onboarding

Purpose: Promote 6E with honest DXY/session dependency handling.

Required:

- `preserved_6e_phase1` runtime profile.
- 6E fixture artifacts.
- Numeric DXY source decision.
- Session sequence fields.
- Asia/London/NY state.
- Thin-liquidity after London close handling.

Acceptance:

- Textual DXY alone cannot arm 6E.
- Missing session sequence blocks 6E.
- DXY unavailable is explicit and fail-closed.
- 6E uses preserved engine path.

Suggested prompt:

`PROMPT 075 - Onboard 6E Runtime Profile and DXY Session Gate`

Expected commit:

`Onboard 6E runtime profile`

## C5. MGC Runtime/Profile Onboarding

Purpose: Promote MGC with honest DXY/yield dependency handling.

Required:

- `preserved_mgc_phase1` runtime profile.
- MGC fixture artifacts.
- Numeric DXY source decision.
- Numeric yield source decision.
- Micro Gold labeling.
- Micro Gold risk/tick metadata.
- Fear catalyst state as explicit available/unavailable field.

Acceptance:

- MGC does not depend on GC.
- MGC is never labeled GC.
- Missing required DXY/yield context blocks relevant triggers.
- MGC uses preserved engine path.

Suggested prompt:

`PROMPT 076 - Onboard MGC Runtime Profile and DXY Yield Gate`

Expected commit:

`Onboard MGC runtime profile`

---

# Band D: Evidence and Live Rehearsal

## D1. Evidence and Replay from Cockpit Events

Purpose: Ensure the cockpit does not just display state but leaves a reviewable trail.

Persisted event classes:

- stream_connected.
- stream_disconnected.
- subscription_added.
- quote_stale.
- quote_recovered.
- bar_closed.
- trigger_approaching.
- trigger_touched.
- trigger_armed.
- trigger_query_ready.
- trigger_invalidated.
- query_submitted.
- pipeline_result.
- operator_note_added.
- session_reset.

Acceptance:

- No synthetic replay appears as real.
- Missing replay data blocks replay.
- Trigger transition logs are deterministic.
- Evidence is contract-attributed.
- ES evidence cannot bleed into NQ, CL, 6E, or MGC.

Suggested prompt:

`PROMPT 077 - Wire Cockpit Events into Evidence Replay`

Expected commit:

`Wire cockpit evidence replay`

## D2. Manual Live Rehearsal Harness, Dry-Run First

Purpose: Prepare live rehearsal without accidentally touching credentials or creating default-live behavior.

Required:

- Explicit live flag.
- Safe symbol list display without secrets.
- Dry-run config validation.
- Redacted provider diagnostics.
- No credential/token contents printed.
- No auth payload printing.
- No default launch change.

Acceptance:

- Dry-run proves what will be attempted.
- Live path remains opt-in.
- CI remains non-live.
- No repeated login on UI refresh.

Suggested prompt:

`PROMPT 078 - Prepare Five-Contract Live Rehearsal Harness Dry Run`

Expected commit:

`Prepare five-contract live rehearsal dry run`

## D3. Manual Five-Contract Live Rehearsal

Purpose: Prove the workstation against real Schwab behavior.

This step requires explicit user authorization and should not be run automatically.

Rehearsal checks:

- One stream connection.
- Subscribe ES, NQ, CL, 6E, MGC.
- LEVELONE_FUTURES updates or exact reason per contract.
- CHART_FUTURES updates or exact reason per contract.
- Cache freshness.
- Marimo UI refreshes from cache.
- No repeated login per refresh.
- ES trigger state updates.
- CL lockout displays if relevant.
- NQ relative strength updates or blocks clearly.
- 6E DXY/session fields populate or block clearly.
- MGC DXY/yield fields populate or block clearly.
- Query gate remains fail-closed.
- No unsupported contract appears.
- No false READY state.
- No secrets printed.

Suggested prompt:

`PROMPT 079 - Run Explicit Five-Contract Schwab Live Rehearsal`

Expected commit:

`Record five-contract live rehearsal result`

---

# Band E: Release Hardening

## E1. Test Harness and CI Consolidation

Purpose: Convert the accumulated vertical slices into stable release checks.

Required suites:

- Contract universe guards.
- Runtime profile registry.
- Live observable schema.
- Stream manager and cache.
- Chart bar builder.
- Trigger state engine.
- Pipeline query gate provenance.
- Operator cockpit rendering.
- Blocked-state display.
- Evidence/replay attribution.
- Redaction.
- Launch default non-live.
- No fixture fallback after live failure.

Acceptance:

- CI passes without credentials.
- Live tests require explicit opt-in.
- Broad verification is reserved for final checkpoints.
- Changed Python files pass Ruff.
- No unrelated lint cleanup.

Suggested prompt:

`PROMPT 080 - Consolidate Release Candidate Test Harness`

Expected commit:

`Consolidate release test harness`

## E2. Performance Review Layer, Minimal V1

Purpose: Add review usefulness without pretending the system has proven statistical edge.

Required:

- NO_TRADE rate.
- Trigger-to-query rate.
- Query-to-approval rate.
- Approval-to-execution rate, only if manually entered.
- Manual outcome fields, optional.
- Failure taxonomy.
- Pause criteria.
- Explicit insufficient-sample warnings.

Acceptance:

- System decision quality is separate from trader execution quality.
- Metrics do not claim edge before sample size exists.
- Manual execution/outcome entry does not become broker integration.
- No P&L/account automation.

Suggested prompt:

`PROMPT 081 - Add Minimal Performance Review Layer`

Expected commit:

`Add performance review layer`

## E3. Release Candidate Cut

Purpose: Finalize the personal workstation candidate.

Release candidate acceptance:

- ES supported.
- NQ supported.
- CL supported.
- 6E supported.
- MGC supported.
- ZN excluded.
- GC excluded.
- Persistent Schwab stream supported.
- LEVELONE_FUTURES supported or blocks with exact reason.
- CHART_FUTURES supported or blocks with exact reason.
- Snapshot v2 populated or blocks clearly.
- Bar builder drives acceptance/rejection logic.
- Cockpit is primary workflow.
- Query gate enables only on deterministic produced QUERY_READY provenance.
- Pipeline decisions remain engine-derived.
- Manual query only.
- Manual execution only.
- No auto-order behavior.
- Audit/replay works from attributed records.
- Manual live rehearsal result is recorded.

Suggested prompt:

`PROMPT 082 - Cut NTB Marimo Console Release Candidate`

Expected commit:

`Cut NTB Marimo Console release candidate`

---

# Prompt Queue Summary

| Prompt | Roadmap Band | Title | Effort | Risk | Expected Commit |
|---:|---|---|---|---|---|
| 065 | A1 | Audit R14 Operator Workspace Redesign Readiness | High | Medium | Audit R14 operator workspace readiness |
| 066 | A2 | Define R14 Cockpit View Model Contract | High | Medium | Define R14 cockpit view model contract |
| 067 | A3 | Build R14 Primary Operator Cockpit Shell | High | Medium | Build R14 operator cockpit shell |
| 068 | A4 | Surface Operator-Readable Blocked States | High | Medium | Surface operator blocked-state reasons |
| 069 | B1 | Audit Five-Contract Schwab Stream Capability | High | Medium | Audit five-contract Schwab stream capability |
| 070 | B2 | Implement CHART_FUTURES Bar Contract and Blocking Semantics | Xtra High | High | Add chart futures bar contract |
| 071 | B3 | Complete Five-Contract Live Observable Snapshot Coverage | Xtra High | High | Complete five-contract observable coverage |
| 072 | C1 | Prove ES Live Thesis Cockpit Vertical Slice | High | Medium | Prove ES live thesis cockpit slice |
| 073 | C2 | Prove CL Live Thesis Cockpit Slice | High | Medium | Prove CL live thesis cockpit slice |
| 074 | C3 | Onboard NQ Runtime Profile and Relative-Strength Gate | High | Medium | Onboard NQ runtime profile |
| 075 | C4 | Onboard 6E Runtime Profile and DXY Session Gate | High | Medium | Onboard 6E runtime profile |
| 076 | C5 | Onboard MGC Runtime Profile and DXY Yield Gate | High | Medium | Onboard MGC runtime profile |
| 077 | D1 | Wire Cockpit Events into Evidence Replay | High | Medium | Wire cockpit evidence replay |
| 078 | D2 | Prepare Five-Contract Live Rehearsal Harness Dry Run | Xtra High | High | Prepare five-contract live rehearsal dry run |
| 079 | D3 | Run Explicit Five-Contract Schwab Live Rehearsal | Xtra High | High | Record five-contract live rehearsal result |
| 080 | E1 | Consolidate Release Candidate Test Harness | High | Medium | Consolidate release test harness |
| 081 | E2 | Add Minimal Performance Review Layer | High | Medium | Add performance review layer |
| 082 | E3 | Cut NTB Marimo Console Release Candidate | Xtra High | High | Cut NTB Marimo Console release candidate |

## Orchestration Rule Going Forward

Default mode:

- One numbered Terminal command at a time for diagnostics, small audits, and narrow fixes.
- Codex only for repo-scale inspection, multi-file implementation, repeated test iteration, complex failure recovery, stream/auth/data-integrity work, or cockpit implementation.

Stop and request a diagnostic command only when:

- `git status` is dirty and ownership is unclear.
- Tests fail in an unrelated area and source is unknown.
- A live provider step would require unsafe credential inspection or printed identifiers.
- A step would change the manual-only/no-execution boundary.
- A step would modify source/ntb_engine.
- A roadmap step no longer matches repo reality.
- ZN or GC would be re-promoted.
- A missing field or stale quote could still produce QUERY_READY.

## Definition of Done

The app is real and ready when an experienced trader can launch the Marimo workstation, see ES, NQ, CL, 6E, and MGC only, load the session premarket plan, receive live Schwab futures updates, see every contract’s thesis state and block reason, manually query the preserved pipeline only when deterministic live conditions justify it, review the result, add notes, and replay the full session without fabricated data, hidden decision authority, default-live behavior, or any trade-execution automation.

