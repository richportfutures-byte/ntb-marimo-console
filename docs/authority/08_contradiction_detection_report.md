# Contradiction Detection Report

**Authority document set:** `docs/authority/`  
**This document:** `contradiction_detection_report.md`  
**Generated:** 2026-03-28  
**Status:** BINDING FOR REVIEW PROCESS

## Executive Reality Check

R00 resolves the authority contradiction between the stale ES/ZN/CL phase-support framing and the new final product target universe.

The active final target support universe is now:

- `ES`
- `NQ`
- `CL`
- `6E`
- `MGC`

`ZN` is excluded/historical. `GC` is excluded and must not be used as a synonym for `MGC`.

This report now focuses on:

1. confirming that the authority reset distinguishes final target support from current runtime profiles
2. keeping terminology and boundaries normalized
3. recording remaining implementation deltas without claiming they are complete in R00

## Resolved Contradictions Register

| ID | Conflict | Resolution | Canonical Rule |
|---|---|---|---|
| CD-01 | Pre-market / Watchman was first deferred, then required | Resolved earlier and retained | Pre-market brief and Watchman gating remain governed by fail-closed Validator output when runtime work is in scope. |
| CD-02 | Bounded target looked narrower than later requirements | Resolved by amendment | R00 is authority reset only; future runtime/profile/live-gating work must be separately scoped. |
| CD-03 | Six-contract phase closure was required even though the engine freeze blocked truthful completion | Superseded by R00 | Final target support is `ES`, `NQ`, `CL`, `6E`, and `MGC`; current app-profile support remains separate. |
| CD-04 | Broader Watchman generation/scoring was marked THIS PHASE even though no frozen-engine path could satisfy it | Resolved earlier and retained | R00 does not implement engine-owned Watchman generation/scoring. |
| CD-05 | Full Stage E audit-schema completeness was marked THIS PHASE even though the frozen engine writer does not emit that shape | Resolved earlier and retained | R00 does not expand the frozen engine writer. |
| CD-06 | Engine-authored `post_entry_management` was required even though the frozen engine schemas do not expose it | Resolved earlier and retained | Engine-authored `post_entry_management` remains deferred. |
| CD-07 | "Console" was used ambiguously | Resolved and retained | Terms remain locked: Engine, App surface / operator workspace, Console. |
| CD-08 | Authority docs bound final support to ES/ZN/CL while the new target universe is ES/NQ/CL/6E/MGC | Resolved by R00 authority reset | `ZN` is excluded/historical; `NQ`, `6E`, and `MGC` are required onboarding targets. |
| CD-09 | Gold support could be confused between `GC` and `MGC` | Resolved by R00 authority reset | `MGC` is the gold contract for this application; `GC` is excluded and not a synonym. |

## Structural Contradiction Checks

### Check 1 - Does the phase definition match R00?

**Assessment:** Clean. The phase definition now states that R00 is documentation/authority reset only and does not claim runtime implementation.

### Check 2 - Does the support matrix match the phase scope contract?

**Assessment:** Clean. Both documents bind final target support to `ES`, `NQ`, `CL`, `6E`, and `MGC`; classify `ZN` as excluded/historical; and classify `GC` as excluded.

### Check 3 - Does the acceptance matrix test only the R00 target?

**Assessment:** Clean. R00 acceptance checks authority reset, current-state truthfulness, and doctrine preservation. Runtime checks are retained only as current-state factual regression slices.

### Check 4 - Does the deferred register distinguish required onboarding from deferred work?

**Assessment:** Clean. `NQ`, `6E`, and `MGC` are required onboarding targets, while engine-owned Watchman, Stage E expansion, and other future items remain deferred.

### Check 5 - Is anything still tagged R00 that would require reopening `ntb_engine`?

**Assessment:** Clean. R00 acceptance can be achieved without engine, runtime profile, Schwab adapter, or stream manager changes.

## Normalization Actions

### ND-01 - Terminology stays locked

All docs must use:

- Engine
- App surface / operator workspace
- Console

### ND-02 - Baseline remains descriptive only

The baseline records what exists. It does not redefine the final target or imply that current `ZN` runtime support is final target support.

### ND-03 - Deferred does not mean secretly in progress

Engine-blocked items in the deferred register may not reappear in target code as partial stand-ins, shadow systems, or presentation-only claims.

### ND-04 - Required onboarding is not optional

`NQ`, `6E`, and `MGC` are required final-target onboarding work. They are not generic deferred extras, and they are not engine-missing contracts.

### ND-05 - Gold naming remains exact

`MGC` must be used for the application's gold contract. `GC` is excluded and must not be introduced as an alias or supported label.

## Implementation Deltas, Not Contradictions

| ID | Current-State Finding | Authority Requirement | Classification |
|---|---|---|---|
| ID-01 | ES and CL are current app-profile-supported contracts | Final target requires ES and CL plus future live workstation upgrades | Required onboarding |
| ID-02 | NQ, 6E, and MGC are fixture-safe app-profile-supported foundations | Final target still requires future live workstation networking/startup/authorization work | Required live-workstation upgrades |
| ID-03 | ZN is an operational preserved profile today | ZN is excluded from final target support | Required scope cleanup |
| ID-04 | GC is not present today | GC must remain excluded and not alias MGC | Required scope cleanup |
| ID-05 | Recent-session evidence, Run History, and Audit / Replay are real and local | Evidence/history must remain truthful and fail-closed | Doctrine preservation |
| ID-06 | Manual verification items are still outstanding | Operator sign-off is still required for closure | Acceptance follow-through |

## Review Loop Use

Run this report before any serious implementation cycle and whenever the authority set is amended again.

The contradiction review is complete only when:

1. no R00 item requires reopening `ntb_engine`
2. no support-matrix item conflicts with the current phase contract
3. the acceptance matrix still proves the authority reset honestly
4. the baseline still distinguishes authority from current code reality
5. `MGC` remains the only gold contract in the final target universe

## Final Canonical Position

The final product target is a Schwab-backed Marimo futures workstation for `ES`, `NQ`, `CL`, `6E`, and `MGC`. `ZN` is excluded/historical, `GC` is excluded, the engine remains sole decision authority, execution remains manual-only, and runtime behavior must remain fail-closed.
