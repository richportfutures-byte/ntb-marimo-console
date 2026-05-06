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
- `preserved_zn_phase1`: operational current preserved legacy/historical profile
- `preserved_cl_phase1`: operational current preserved profile
- `NQ`, `6E`, and `MGC`: engine-supported but not final app-profile-supported yet
- current final target mismatch: `NQ`, `6E`, and `MGC` are required final target onboarding contracts but do not yet have app-profile support
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

- preserved ES, ZN, and CL profiles can execute the bounded preserved-engine query path
- profile switching across ES, ZN, and CL is implemented and fail-closed as current-state behavior
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
| `NQ` app-profile support | Not implemented |
| `6E` app-profile support | Not implemented |
| `MGC` app-profile support | Not implemented |
| Future live workstation upgrades for current `ES` support | Not implemented in R00 |
| Future live workstation upgrades for current `CL` support | Not implemented in R00 |
| Additional `ZN` exclusion cleanup beyond selector/final-target guard | Not implemented |
| Additional `GC` exclusion guard beyond target-owned contract universe | Not implemented |
| Wiring persistent stream manager into live workstation startup | Not implemented |

## Docs vs Code Delta

| Documentation State | Actual Code State | Resolution |
|---|---|---|
| Earlier authority set required full engine-owned Watchman generation/scoring in this phase | Target code implements only the app-surface Watchman gate truthfully | Requirement remains deferred |
| Earlier authority set required final support around ES, ZN, and CL | Runtime profiles contain ES, ZN, and CL, but engine schema also includes NQ, 6E, and MGC | Authority reset supersedes ES/ZN/CL as final target; final target is ES, NQ, CL, 6E, MGC |
| Earlier authority set treated NQ, 6E, and MGC as deferred/non-target for phase closure | NQ, 6E, and MGC are engine-supported but not app-profile-supported | Reclassified as required onboarding targets |
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
