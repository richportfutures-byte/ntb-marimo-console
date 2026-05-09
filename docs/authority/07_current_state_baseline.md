# Current State Baseline

**Authority document set:** `docs/authority/`  
**This document:** `current_state_baseline.md`  
**Generated:** 2026-03-28  
**Status:** INFORMATIONAL

> [!WARNING]
> This document describes what exists today. It is not a requirements document. Requirements are defined by `current_phase_scope_contract.md`. If this document conflicts with verified code, the code is the ground truth and this document must be updated.

## What the Code Does Today

### Engine Schema and Contract Universe

- engine schema includes `ES`, `NQ`, `CL`, `ZN`, `6E`, and `MGC`
- target adapter contract typing also includes `ES`, `NQ`, `CL`, `ZN`, `6E`, and `MGC`
- `GC` is not present as an engine schema contract or target adapter contract
- the final product target has been reset to `ES`, `NQ`, `CL`, `6E`, and `MGC`
- `ZN` exists in code today but is excluded from final target support
- `GC` is excluded and must not be used as a synonym for `MGC`

### Runtime Profiles and Support Boundary

- `fixture_es_demo`: available as a fixture/demo runtime path
- `preserved_es_phase1`: operational current preserved profile
- `preserved_nq_phase1`: fixture-safe preserved profile foundation
- `preserved_6e_phase1`: fixture-safe preserved profile foundation
- `preserved_mgc_phase1`: fixture-safe preserved profile foundation
- `preserved_zn_phase1`: operational current preserved legacy/historical profile
- `preserved_cl_phase1`: operational current preserved profile
- `ZN`: current preserved profile exists, but it is now excluded from final target support
- `GC`: not present and excluded
- target-owned `contract_universe.py` now encodes final target contracts, legacy/historical contracts, and never-supported contracts
- final-target operator selector surfaces exclude the legacy `ZN` profile while preserving direct legacy runtime availability

### Windows Runtime Ownership

- target bootstrap/setup on Windows is reproducible
- direct launch uses a target-owned Marimo runtime path under `target/ntb_marimo_console/.state/marimo`
- direct launch no longer depends on the denied host-level Marimo config path
- a single-entry Windows acceptance harness exists and runs dedicated regression slices for the Watchman gate, JSONL-backed Run History / Audit Replay, and retained evidence

### Watchman and Pre-Market Layer

- current preserved profiles render target-owned pre-market briefs
- a target-owned Watchman validator exists for the app surface
- `mo.stop()` is wired to Validator output in the real Marimo entry path
- raw brief `status` does not authorize the gate
- broader engine-owned Watchman brief/scoring generation is not implemented in target code and remains deferred rather than required in R00

### Preserved Engine Execution Path

- preserved ES, NQ, 6E, MGC, ZN, and CL profiles can execute the bounded preserved-engine query path
- profile switching across ES, NQ, 6E, MGC, ZN, and CL is implemented and fail-closed as current-state behavior
- stale per-profile session state is cleared on successful switch
- this current-state behavior does not make `ZN` final target support

### Run History, Audit Replay, and Recent Session Evidence

- preserved-profile Run History reads real local JSONL-backed rows
- preserved-profile Audit / Replay reads from real local JSONL-backed records and blocks if missing
- recent-session evidence is durable across app restarts
- retained recent-session evidence can be cleared explicitly
- current-session evidence and restored-prior-run evidence remain distinct in the UI

### Stream Manager Foundation

- target-owned stream manager foundation exists under `market_data/`
- default launch remains non-live and disabled
- live start requires explicit opt-in and an injected client
- Marimo refresh is modeled as a cache snapshot read, not login or subscription
- tests cover idempotent start, one-login discipline, fail-closed event/cache states, and redaction
- R03 does not implement default real Schwab WebSocket networking or execution/account/order behavior

### Live Observable Snapshot v2

- target-owned live observable snapshot v2 contract exists under `live_observables/`
- snapshot v2 reads R03 stream-cache snapshots and does not start login, subscription, or networking
- primary contract map is limited to `ES`, `NQ`, `CL`, `6E`, and `MGC`
- `ZN` and `GC` are excluded from snapshot v2 primary contract output
- missing required quote fields, stale timestamps, provider block states, and symbol mismatch fail closed through blocking reasons
- R04 does not implement `CHART_FUTURES` bars, trigger-state logic, pipeline query authorization, or UI redesign

### CHART_FUTURES Bar Builder Foundation

- target-owned CHART_FUTURES bar builder foundation exists under `market_data/`
- fixture-normalized one-minute bars can be validated and aggregated into deterministic completed five-minute bars
- current building five-minute bars remain separate from completed five-minute bars
- partial bars, gaps, malformed records, stale data, out-of-order input, symbol mismatch, and excluded contracts fail closed through explicit blocking reasons
- `ZN` and `GC` are excluded from final target bar state, and `GC` is not aliased to `MGC`
- R05 does not wire bar state into trigger-state logic, pipeline query authorization, live networking, or UI redesign

### ES Live Workstation Foundation

- target-owned ES live workstation foundation exists under `live_workstation/`
- the foundation is a deterministic read-model layer only; it is not a decision authority
- it consumes fixture or mocked ES quote, live observable quality, completed bar state, preserved premarket artifact, event lockout, and explicit trigger inputs
- it can report `UNAVAILABLE`, `DORMANT`, `APPROACHING`, `TOUCHED`, `ARMED`, `QUERY_READY`, `INVALIDATED`, `BLOCKED`, `STALE`, `LOCKOUT`, and `ERROR`
- `QUERY_READY` is a read-model state only and does not enable pipeline query authorization
- completed five-minute confirmation requires completed one-minute support; partial or building bars do not count
- missing artifacts, stale data, malformed data, unsupported contracts, excluded contracts, and incomplete confirmation fail closed with stable blocking reasons
- default launch remains non-live and no real Schwab networking is opened by this layer
- no trade, broker, order, execution, fill, account, or P&L behavior is added
- the preserved engine remains the sole decision authority

### NQ Live Workstation Foundation

- target-owned NQ live workstation foundation exists under `live_workstation/`
- the foundation is deterministic and requires explicit NQ quote, ES quote, NQ anchor, ES anchor, completed bar, preserved artifact, trigger, and event-lockout inputs
- `relative_strength_vs_es` is computed only from explicit anchors and quote prices
- absolute NQ price action alone cannot produce `QUERY_READY` when ES-relative confirmation is required
- `QUERY_READY` is a read-model state only and does not enable pipeline query authorization
- missing ES live data, missing NQ/ES anchors, stale data, malformed data, unsupported contracts, excluded contracts, and incomplete confirmation fail closed
- default launch remains non-live and no real Schwab networking is opened by this layer
- no trade, broker, order, execution, fill, account, or P&L behavior is added

### 6E Live Workstation Foundation

- target-owned 6E live workstation foundation exists under `live_workstation/`
- the foundation is deterministic and requires explicit 6E quote, numeric DXY state, DXY source label, completed bar, Asia/London/NY session sequence, session ranges, thin-liquidity state, preserved artifact, trigger, and event-lockout inputs
- textual DXY context is not sufficient when numeric DXY is required
- absolute 6E price action alone cannot produce `QUERY_READY` when DXY/session confirmation is required
- `QUERY_READY` is a read-model state only and does not enable pipeline query authorization
- missing numeric DXY, missing DXY source label, missing session sequence, missing range fields, active blocking thin-liquidity state, stale data, malformed data, unsupported contracts, excluded contracts, and incomplete confirmation fail closed
- default launch remains non-live and no real Schwab networking is opened by this layer
- no trade, broker, order, execution, fill, account, or P&L behavior is added

### MGC Live Workstation Foundation

- target-owned MGC live workstation foundation exists under `live_workstation/`
- the foundation is deterministic and requires explicit MGC quote, numeric DXY state, numeric yield state, completed bar, preserved artifact, trigger, and event-lockout inputs
- MGC is treated as Micro Gold only and is not mapped to `GC`
- textual DXY or yield context is not sufficient when numeric macro context is required
- missing fear-catalyst state blocks only when the trigger declares that dependency
- absolute MGC price action alone cannot produce `QUERY_READY` when DXY/yield confirmation is required
- unsupported footprint, DOM, sweep, cumulative delta, and aggressive order-flow evidence are explicitly unavailable and are not inferred from CHART_FUTURES or Level One quote data
- `QUERY_READY` is a read-model state only and does not enable pipeline query authorization
- missing numeric DXY, missing numeric yield, missing required fear-catalyst state, stale data, malformed data, unsupported contracts, excluded contracts, and incomplete confirmation fail closed
- default launch remains non-live and no real Schwab networking is opened by this layer
- no trade, broker, order, execution, fill, account, or P&L behavior is added

### Primary App Surface

- startup, workflow, profile, and evidence surfaces render readably
- current profiles and not-current candidates are surfaced readably
- raw JSON remains confined to secondary/debug surfaces

### Tests and Acceptance

- target regression and acceptance coverage exists for:
  - supported profile listing
  - blocked/not-current candidate audit
  - current supported-profile preflight
  - validator-driven `mo.stop()` gate behavior
  - JSONL-backed run history / audit replay
  - recent-session evidence persistence and clear behavior
  - direct launch-path coherence on Windows

## What R00 Requires That Is Confirmed Not Yet Done

| Item | Status |
|---|---|
| Manual verification items in `acceptance_matrix.md` | Not yet confirmed by operator |
| Final release-candidate acceptance run from a clean workspace | Requires execution at sign-off time |

## Final Target Work Confirmed Not Yet Done

| Item | Status |
|---|---|
| `NQ` app-profile support | R08 preserved profile and read-model foundation exists; live networking/startup wiring and authorization remain not implemented |
| `6E` app-profile support | R09 preserved profile and read-model foundation exists; live networking/startup wiring and authorization remain not implemented |
| `MGC` app-profile support | R10 preserved profile and read-model foundation exists; live networking/startup wiring and authorization remain not implemented |
| Future live workstation upgrades for current `ES` support | R06 read-model foundation exists; live networking/startup wiring and authorization remain not implemented |
| Future live workstation upgrades for current `CL` support | Not implemented in R00 |
| Additional `ZN` exclusion cleanup beyond selector/final-target guard | Not implemented |
| Additional `GC` exclusion guard beyond target-owned contract universe | Not implemented |
| Wiring persistent stream manager into live workstation startup | Not implemented |
| Trigger-state gate wiring from completed bar facts | Not implemented |

## Docs vs Code Delta

| Documentation State | Actual Code State | Resolution |
|---|---|---|
| Earlier authority set required full engine-owned Watchman generation/scoring in this phase | Target code implements only the app-surface Watchman gate truthfully | Requirement remains deferred |
| Earlier authority set required final support around ES, ZN, and CL | Runtime profiles contain ES, ZN, and CL, but engine schema also includes NQ, 6E, and MGC | Authority reset supersedes ES/ZN/CL as final target; final target is ES, NQ, CL, 6E, MGC |
| Earlier authority set treated NQ, 6E, and MGC as deferred/non-target for phase closure | NQ, 6E, and MGC now have profile foundations | Reclassified as final target profile foundations |
| Earlier authority set treated ZN as required current support | ZN runtime profile exists today | Reclassified as excluded/historical for final target support |
| Earlier docs did not explicitly guard GC | GC is not present in engine or target contract typing | GC is explicitly excluded and not a synonym for MGC |
| R01 documented ZN/GC exclusion but had no target-owned executable guard | `contract_universe.py` now classifies final, legacy, and never-supported contracts | Final-target selector/report surfaces can use executable policy without deleting engine/runtime history |
| Earlier authority set required full Stage E audit schema completeness in this phase | Frozen engine writes a bounded JSONL run-history record shape | Full Stage E schema expansion deferred |
| Earlier authority set required engine-owned `post_entry_management` output | Frozen engine schemas do not expose that output | Requirement deferred |

## Stale Documents That Must Be Superseded

Use the supersession header from `authority_protocol.md` on:

- phase execution plans
- project freeze documents
- vision/spec files that still read like binding requirements
- READMEs that contain scope definitions
- any document that lists in-scope or deferred items without citing the authority set

## Update Rules

Update this document only when:

1. a current runtime profile regresses or a new one is truly added under a future amendment
2. an acceptance item is confirmed complete
3. R00 closes
4. a future authority amendment changes the final target or app-profile boundary again

Do not update this document to reflect aspiration. Every entry must remain factual and verifiable.
