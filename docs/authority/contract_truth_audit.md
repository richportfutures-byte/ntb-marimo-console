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
| NQ | Final target | Yes | Yes | No | No | Onboard profile and ES-relative live gating |
| CL | Final target | Yes | Yes | Yes: `preserved_cl_phase1` | Partial | Live upgrade |
| 6E | Final target | Yes | Yes | No | No | Onboard profile and DXY/session gating |
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
- preserved `ZN` through `preserved_zn_phase1`
- preserved `CL` through `preserved_cl_phase1`

`NQ`, `6E`, and `MGC` profile onboarding remains future work. They require onboarding rather than engine creation.

## Live Gating Finding

Current app/live gating is not complete for the final universe.

Known blockers, stated at the level already present in code and authority docs:

- `NQ` requires ES-relative live observable support.
- `6E` requires numeric DXY and session-sequence support.
- `MGC` requires numeric DXY and yield context.

These blockers are not implemented by R01, and this audit does not claim they are implemented.

## ZN and GC Boundary

`ZN` exists today in engine schema, prompt/system-spec coverage, fixtures, and the preserved runtime profile `preserved_zn_phase1`, but it is historical/excluded and is not part of final target support.

`GC` is not present as an engine schema literal, Stage A/B prompt, system-spec target, runtime profile, or current app/live-gating target. `GC` must not be added or conflated with `MGC`.

## Next Roadmap Justification

R02 is justified only as scoped `ZN`/`GC` exclusion cleanup planning or implementation.

Stream manager and live runtime work are premature until this truth audit is committed.
