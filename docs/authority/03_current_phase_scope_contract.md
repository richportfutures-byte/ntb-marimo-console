# Current Phase Scope Contract

**Authority document set:** `docs/authority/`  
**This document:** `current_phase_scope_contract.md`  
**Generated:** 2026-03-28  
**Status:** BINDING

## Phase Definition Sentence

R00 is complete when the authority document set truthfully resets the final product contract universe to `ES`, `NQ`, `CL`, `6E`, and `MGC`; classifies `ZN` and `GC` as excluded from the final target workflow; preserves the engine as sole decision authority; preserves manual-only execution; preserves fail-closed runtime doctrine; and makes clear that runtime/profile/live-gating implementation is future roadmap work, not complete in R00.

## Gate Answers

| Gate | Question | Answer | Tag |
|---|---|---|---|
| Gate 1 | Product target for this phase | Documentation/authority reset only. No runtime behavior, Schwab adapter behavior, stream manager behavior, or engine behavior is implemented in R00. | R00 |
| Gate 2 | Final target support universe | `ES`, `NQ`, `CL`, `6E`, and `MGC` are the final target contracts. `MGC` is the gold contract for this application. | BINDING TARGET |
| Gate 3 | Excluded contracts | `ZN` is excluded/historical. `GC` is excluded and must not be treated as a synonym for `MGC`. | BINDING EXCLUSION |
| Gate 4 | Current runtime profile reality | Current target runtime profiles include fixture `ES`, preserved `ES`, preserved `ZN`, and preserved `CL`; this current-state fact does not define final target support. | CURRENT STATE |
| Gate 5 | Engine freeze and decision authority | No `ntb_engine` changes are authorized in R00. The engine remains sole decision authority for staged evaluation. | THIS PHASE |

## Mandatory R00 Capabilities

### Layer 1 - Authority Reset

- authority docs must name the final target support universe as:
  - `ES`
  - `NQ`
  - `CL`
  - `6E`
  - `MGC`
- authority docs must no longer define the final product target around `ES`, `ZN`, and `CL`
- `ZN` must be classified as excluded/historical, not required final target support
- `GC` must be classified as excluded
- `MGC` must never be described as `GC`, and `GC` must never be used as a synonym for `MGC`
- historical references to `ZN` may remain when clearly classified as current-state, legacy, fixture, or historical evidence

### Layer 2 - Current-State Truthfulness

- R00 must preserve the factual baseline that current runtime profiles include:
  - `fixture_es_demo`
  - `preserved_es_phase1`
  - `preserved_nq_phase1`
  - `preserved_6e_phase1`
  - `preserved_mgc_phase1`
  - `preserved_zn_phase1`
  - `preserved_cl_phase1`
- `ES`, `NQ`, `CL`, `6E`, and `MGC` are current app-profile-supported through fixture-safe foundations that still require future live workstation upgrades
- `NQ`, `6E`, and `MGC` must not be described as engine-missing contracts
- `ZN` may remain in code, fixtures, or tests as a legacy/historical artifact during R00, but it is not final target support
- `GC` is not present as a supported contract and remains excluded

### Layer 3 - Runtime and Live Work Boundary

- R00 does not modify runtime profiles
- R00 does not modify Schwab adapter code
- R00 does not implement stream manager behavior
- R00 does not make default launch live
- R00 does not add broker, order, execution, account, fill, or P&L behavior
- R00 does not delete `ZN` engine code or fixtures
- runtime/profile/live-gating implementation for the final target universe is future roadmap work

### Layer 4 - Preserved Engine and Manual-Only Execution Boundary

- the engine remains the sole decision authority
- the app surface may orchestrate, summarize, and display results, but may not reinterpret or override engine decisions
- the pre-market brief is not a trade signal and does not lower the bar for querying
- all trade execution remains manual-only outside the application
- no automated order entry, modification, cancellation, stop movement, target movement, fill tracking, account tracking, or P&L behavior is introduced

### Layer 5 - Fail-Closed Doctrine

- no fake `READY` gate
- no partial proposal under uncertainty
- no silent fallback
- no fixture fallback after live failure
- no synthetic audit evidence presented as real session history
- no smoothing over engine defects from the app surface
- the 15-second minimum refresh floor remains binding for live refresh behavior when live behavior is implemented or maintained outside R00

## Runtime and Audit Invariants

These invariants are binding and resolve implementation ambiguity:

1. The app surface never becomes a second decision authority.
2. The Watchman gate must fail closed and may not be bypassed by manual status assignment.
3. Every rendered numeric claim in a pre-market brief must trace to named artifact fields.
4. Unsupported, excluded, malformed, blocked, or failed states remain blocked and are surfaced truthfully.
5. Current-session evidence and restored-prior-run evidence must not bleed across profiles.
6. The only acceptable degraded behavior is an explicit blocked or failed state with the exact reason.
7. No operator-facing convenience may fabricate, smooth, or substitute for real preserved-engine behavior, real live-provider behavior, or real local evidence.
8. `GC` must not appear as a supported contract, alias, or display substitute for `MGC`.

## Explicit Exclusions

1. direct connection to NinjaTrader, Tradovate, or any brokerage API
2. auto-submission of ATM strategy parameters
3. programmatic stop or target modification of live positions
4. any automated order entry, modification, or cancellation
5. broker account, fill, position, or P&L behavior
6. cross-contract matrix or comparative dashboard views
7. confidence score as a progress bar or visual sentiment indicator
8. auto-retry logic that relaxes thresholds after rejection
9. any suggested-trade output on `NO_TRADE`
10. custom theming, branded color systems, animated transitions
11. responsive layout for non-desktop viewports
12. multi-tab navigation or dashboard widgets
13. real-time chart overlays
14. automated JSONL analytics or cross-session performance attribution
15. direct NinjaTrader platform integration for packet assembly
16. multi-session regime tracking
17. live Stage E ingestion beyond append-only local JSONL writes
18. engine-owned Watchman brief generation, WatchmanScores, N1-N6 modeling, and `overall_market_readiness` in R00
19. Thesis Registry sharing/drift-proofing in R00
20. engine-authored `post_entry_management` output in R00
21. full Stage E audit schema expansion beyond the frozen engine writer in R00
22. promotion of `NQ`, `6E`, or `MGC` to current app-profile-supported status in R00
23. `ZN` as final target support
24. `GC` as any supported contract, target contract, synonym, or alias for `MGC`

## Engine Boundary Rules

1. The engine, `ntb_engine`, is frozen for R00.
2. Any engine defect that cannot be resolved without engine modification is not worked around from the app surface.
3. The app surface does not mask, route around, or compensate for engine defects by inventing replacement decision logic.
4. Acceptance for R00 must be achieved without `ntb_engine` file changes.
5. Console-layer work, formatting, persistence, validation wiring, and observability enhancements must occur outside the engine when they are authorized by a future roadmap step.

## Data Truth Model

| Data Input | Acceptable Source | Notes |
|---|---|---|
| Prior-day OHLC | Truthful preserved artifacts or future truthful live source | Must be schema-valid and manually verifiable |
| Volume profile | Truthful preserved artifacts or future truthful live source | Same rule |
| Overnight session data | Truthful preserved artifacts or future truthful live source | Same rule |
| Volatility context | Truthful preserved artifacts or future truthful live source | Same rule |
| Session-sequence data | Truthful preserved artifacts or future truthful live source | Same rule |
| Macro/event context | Truthful preserved artifacts or future truthful live source | Real-provider expansion remains separately scoped |

Unacceptable simulation includes:

- hardcoded outputs that bypass preserved-engine stage logic
- manually assigning readiness or decision fields to bypass gating
- synthetic run history or audit replay presented as real local JSONL evidence
- fixture fallback after live failure
- fixtures that clear gates that the validator or preserved engine would fail

## Three-Layer Architecture

| Layer | Name | Role |
|---|---|---|
| 1 | Engine | Frozen preserved engine path. Sole decision authority for bounded pipeline execution. |
| 2 | App surface / operator workspace | Deployed Marimo interface used during the session |
| 3 | Console | Diagnostic panel only. Hidden debug and observability surface. |
