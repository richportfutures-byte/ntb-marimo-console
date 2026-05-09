# Contract Truth Audit

**Authority document set:** `docs/authority/`
**This document:** `contract_truth_audit.md`
**Generated:** 2026-05-06
**Status:** INFORMATIONAL AUDIT

## Purpose

This is a factual audit after the R00 authority reset. It is not an implementation plan and does not authorize runtime, engine, Schwab adapter, stream manager, broker, order, execution, account, fill, or P&L behavior.

The final target contracts are:

- `ES`
- `NQ`
- `CL`
- `6E`
- `MGC`

`ZN` and `GC` are excluded from final target support. `ZN` remains present today as historical implementation evidence. `GC` is not implemented and must not be added or conflated with `MGC`.

## Source Basis

This audit uses these exact files to establish truth:

- `source/ntb_engine/src/ninjatradebuilder/schemas/inputs.py`
- `source/ntb_engine/STAGE_6_FINAL_SYSTEM_SPEC.md`
- `source/ntb_engine/src/ninjatradebuilder/prompt_assets.py`
- `target/ntb_marimo_console/src/ntb_marimo_console/runtime_profiles.py`
- `target/ntb_marimo_console/src/ntb_marimo_console/adapters/contracts.py`
- `target/ntb_marimo_console/src/ntb_marimo_console/preserved_contract_onboarding.py`
- `docs/authority/04_support_matrix.md`
- `docs/authority/07_current_state_baseline.md`

## Contract Coverage Matrix

| Contract | Final target status | Engine schema literal | Stage A/B prompt/system spec | Runtime profile today | Current app/live gating status | Required final action |
|---|---|---|---|---|---|---|
| ES | Final target | Yes | Yes | Yes: `fixture_es_demo`, `preserved_es_phase1` | Partial | Live upgrade |
| NQ | Final target | Yes | Yes | Yes: `preserved_nq_phase1` | Partial | Live upgrade |
| CL | Final target | Yes | Yes | Yes: `preserved_cl_phase1` | Partial | Live upgrade |
| 6E | Final target | Yes | Yes | Yes: `preserved_6e_phase1` | Partial | Live upgrade |
| MGC | Final target; not `GC` | Yes | Yes | No | No | Onboard profile and DXY/yield gating |
| ZN | Excluded/historical | Yes | Yes | Yes today: `preserved_zn_phase1` | Partial/historical | Remove from final target workflow later without deleting engine in R01 |
| GC | Excluded | No | No | No | No | Keep excluded; no engine schema literal, prompt, runtime profile, or live gating |

## Engine Universe Finding

There is no missing engine-universe issue for `ES`, `NQ`, `CL`, `6E`, and `MGC`. The engine schema literal and Stage A/B prompt/system-spec coverage exist for those final target contracts.

`GC` is absent from the engine schema and prompt/system-spec universe and is intentionally excluded.

## Runtime Profile Finding

Runtime profiles currently include:

- fixture `ES` through `fixture_es_demo`
- preserved `ES` through `preserved_es_phase1`
- preserved `NQ` through `preserved_nq_phase1`
- preserved `6E` through `preserved_6e_phase1`
- preserved `ZN` through `preserved_zn_phase1`
- preserved `CL` through `preserved_cl_phase1`

`MGC` profile onboarding remains future work. `NQ` and `6E` now have preserved profile foundations, but live startup wiring and trade authorization remain out of scope. Remaining contracts require onboarding rather than engine creation.

R02 adds a target-owned final contract universe guard. That guard does not delete runtime profiles; it separates final-target operator selection from legacy/historical runtime availability.

## Live Gating Finding

Current app/live gating is not complete for the final universe.

Known blockers, stated at the level already present in code and authority docs:

- `NQ` has a deterministic ES-relative read-model/profile foundation; live startup wiring and production ES-relative data remain deferred.
- `6E` has a deterministic numeric-DXY and session-sequence read-model/profile foundation; live startup wiring and production DXY/session data remain deferred.
- `MGC` requires numeric DXY and yield context.

These blockers are not implemented by R02, and this audit does not claim they are implemented.

## ZN and GC Boundary

`ZN` exists today in engine schema, prompt/system-spec coverage, fixtures, and the preserved runtime profile `preserved_zn_phase1`, but it is historical/excluded and is not part of final target support.

`GC` is not present as an engine schema literal, Stage A/B prompt, system-spec target, runtime profile, or current app/live-gating target. `GC` must not be added or conflated with `MGC`.

R02 executable guard status: `ZN` is classified as legacy/historical and excluded from final-target operator selector surfaces. `GC` is classified as never-supported/excluded. `MGC` remains the only gold final target contract and is not mapped to `GC`.

## Next Roadmap Justification

After R02, additional `ZN`/`GC` cleanup is justified only if it is scoped to preserving historical truth while removing remaining final-target ambiguity.

Stream manager and live runtime work remain premature until the final-target onboarding step is explicitly opened.
