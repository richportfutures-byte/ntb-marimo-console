# Current Phase Scope Contract

**Authority document set:** `docs/authority/`  
**This document:** `current_phase_scope_contract.md`  
**Generated:** 2026-03-28  
**Status:** BINDING

## Phase Definition Sentence

The phase is done when the bounded Marimo operator console can launch on Windows, operate truthfully over the frozen preserved-engine path for `preserved_es_phase1`, `preserved_zn_phase1`, and `preserved_cl_phase1`, hard-gate pipeline access through the validator-driven Watchman app surface, show real local JSONL-backed run history and audit replay, persist recent session evidence across restarts, and do all of that fail-closed with no engine changes.

## Gate Answers

| Gate | Question | Answer | Tag |
|---|---|---|---|
| Gate 1 | Product target for this phase | Bounded Marimo operator console containing pre-market surfaces, Watchman gate, bounded preserved-engine execution, and operator evidence/history in one surface | THIS PHASE |
| Gate 2 | Is multi-contract implementation the accepted baseline? | Yes. ES + ZN + CL with explicit profile switching is the accepted structural baseline for this phase. | THIS PHASE |
| Gate 3 | Data reality | Truthful preserved artifacts are acceptable for this phase, including preserved macro/event context. Real-provider macro/event ingestion is deferred. | THIS PHASE |
| Gate 4 | Watchman scope for this phase | In scope as the target-owned app-surface readiness and gating layer only. Full engine-owned Watchman brief/scoring generation is deferred. | THIS PHASE |
| Gate 5 | Engine freeze | Permanent for this phase. No engine changes are authorized. Any requirement that depends on `ntb_engine` changes is deferred or blocking unless the authority set is amended again. | THIS PHASE |

## Mandatory Capabilities

### Layer 1 - Supported Preserved Profiles

- the commissionable preserved profiles for this phase are:
  - `preserved_es_phase1`
  - `preserved_zn_phase1`
  - `preserved_cl_phase1`
- `fixture_es_demo` remains an allowed non-commissioning fixture/demo path
- each supported preserved profile must:
  - resolve through the runtime profile registry
  - pass strict preflight
  - assemble the bounded app shell
  - launch through the documented Windows command path
- blocked contracts must remain blocked and must not appear as ready:
  - `NQ`
  - `6E`
  - `MGC`

### Layer 2 - Pre-Market Brief and Watchman App-Surface Gate

- the app surface renders per-profile pre-market briefs for the supported preserved profiles
- rendered briefs must remain schema-anchored and readable
- the target-owned Watchman validator is the only gate authority for this phase
- gate statuses are limited to:
  - `READY`
  - `NEEDS_REVIEW`
  - `FAILED`
- gate authorization must not trust raw brief `status`
- malformed, incomplete, or unsupported brief content fails closed
- `mo.stop()` is required in the Marimo entry path
- `mo.stop()` reads from Validator output only
- the pipeline section is structurally unreachable when the validator status is `NEEDS_REVIEW` or `FAILED`

### Layer 3 - Marimo App Surface

- renders startup status, active profile identity, supported profiles, and blocked candidates readably
- renders the current supported profile's pre-market brief in app mode
- renders the Watchman readiness/gate status readably
- pipeline execution is operator-initiated and lazy
- the bounded query trigger becomes available only when the validator authorizes the profile as `READY`
- profile switching is explicit, readable, and fail-closed
- stale per-profile session state must not bleed across successful profile switches
- primary app surfaces must not expose raw JSON
- raw JSON and code-editor style diagnostics remain secondary/debug only

### Layer 4 - Preserved Engine Execution Path

- the preserved engine remains the sole decision authority
- the app surface may orchestrate, summarize, and display results, but may not reinterpret or override engine decisions
- supported preserved profiles must be able to run the bounded preserved-engine query path
- bounded preserved-engine execution must surface either:
  - a documented engine-derived trade/risk outcome, or
  - a documented engine-derived `NO_TRADE`
- blocked, failed, or ineligible query paths must fail closed with readable reasons

### Layer 5 - Local JSONL Run History and Audit Replay

- preserved profiles must read run history from real local JSONL-backed records rather than fixture placeholders
- preserved profiles must read audit replay from real local JSONL-backed records rather than fixture placeholders
- if no qualifying JSONL record exists, audit replay must remain blocked rather than fabricated
- local run-history/audit records are append-only for this phase
- the app surface must not expose a destructive clear/reset operation for the preserved-engine JSONL log

### Layer 6 - Recent Session Evidence

- the bounded recent-session evidence ledger persists across app restarts
- evidence remains attributable to the originating profile
- current-session evidence and restored-prior-run evidence remain visibly distinct
- profile switching, reload, reset, blocked, failed, and completed outcomes remain distinct
- operators have an explicit target-owned way to clear retained recent-session evidence
- clearing retained recent-session evidence must not fabricate changes to current in-memory evidence

### Layer 7 - Windows Runtime Ownership

- Windows bootstrap/setup is reproducible from the repository
- the direct launch path uses a target-owned writable Marimo runtime location under `target/ntb_marimo_console/.state/`
- if the target-owned Marimo runtime path cannot be prepared, launch fails readably and explicitly
- the project provides a single-entry Windows acceptance command for this phase

### Layer 8 - CI and Acceptance

- the target test suite and the current bounded regression slices pass with no live LLM dependency
- the single-entry Windows acceptance harness passes
- acceptance must cover:
  - supported profile listing
  - blocked candidate reporting
  - supported-profile preflight
  - validator-driven `mo.stop()` gate behavior
  - JSONL-backed run history / audit replay
  - recent-session evidence persistence and clear behavior
  - direct launch-path coherence using the target-owned Marimo runtime path

## Runtime and Audit Invariants

These invariants are binding for this phase and resolve implementation ambiguity:

1. The app surface never becomes a second decision authority.
2. The Watchman gate must fail closed and may not be bypassed by manual status assignment.
3. Every rendered numeric claim in a pre-market brief must trace to named artifact fields.
4. Blocked profiles remain blocked and are surfaced truthfully.
5. Current-session evidence and restored-prior-run evidence must not bleed across profiles.
6. The only acceptable degraded behavior is an explicit blocked or failed state with the exact reason.
7. No operator-facing convenience may fabricate, smooth, or substitute for real preserved-engine behavior or real local evidence.

## Explicit Exclusions

1. direct connection to NinjaTrader, Tradovate, or any brokerage API
2. auto-submission of ATM strategy parameters
3. programmatic stop or target modification of live positions
4. any automated order entry, modification, or cancellation
5. cross-contract matrix or comparative dashboard views
6. confidence score as a progress bar or visual sentiment indicator
7. auto-retry logic that relaxes thresholds after rejection
8. any suggested-trade output on `NO_TRADE`
9. custom theming, branded color systems, animated transitions
10. responsive layout for non-desktop viewports
11. multi-tab navigation or dashboard widgets
12. real-time chart overlays
13. automated JSONL analytics or cross-session performance attribution
14. direct NinjaTrader platform integration for packet assembly
15. multi-session regime tracking
16. live Stage E ingestion beyond append-only local JSONL writes
17. engine-owned Watchman brief generation, WatchmanScores, N1-N6 modeling, and `overall_market_readiness` in this phase
18. Thesis Registry sharing/drift-proofing in this phase
19. engine-authored `post_entry_management` output in this phase
20. full Stage E audit schema expansion beyond the frozen engine writer in this phase
21. promotion of `NQ`, `6E`, or `MGC` to supported status in this phase

## Engine Boundary Rules

1. The engine, `ntb_engine`, is frozen for this phase.
2. Any engine defect that cannot be resolved without engine modification is not worked around from the app surface.
3. The app surface does not mask, route around, or compensate for engine defects by inventing replacement decision logic.
4. Acceptance for this phase must be achieved without `ntb_engine` file changes.
5. Console-layer work, formatting, persistence, validation wiring, and observability enhancements must occur outside the engine.

## Data Truth Model

| Data Input | Acceptable Source | Notes |
|---|---|---|
| Prior-day OHLC | Truthful preserved artifacts allowed | Must be schema-valid and manually verifiable |
| Volume profile | Truthful preserved artifacts allowed | Same rule |
| Overnight session data | Truthful preserved artifacts allowed | Same rule |
| Volatility context | Truthful preserved artifacts allowed | Same rule |
| Session-sequence data | Truthful preserved artifacts allowed | Same rule |
| Macro/event context | Truthful preserved artifacts allowed for this phase | Real-provider ingestion is deferred to a future engine-enabled phase |

Unacceptable simulation includes:

- hardcoded outputs that bypass preserved-engine stage logic
- manually assigning readiness or decision fields to bypass gating
- synthetic run history or audit replay presented as real local JSONL evidence
- fixtures that clear gates that the validator or preserved engine would fail

## Three-Layer Architecture

| Layer | Name | Role |
|---|---|---|
| 1 | Engine | Frozen preserved engine path. Sole decision authority for bounded pipeline execution. |
| 2 | App surface / operator workspace | Deployed Marimo interface used during the session |
| 3 | Console | Diagnostic panel only. Hidden debug and observability surface. |
