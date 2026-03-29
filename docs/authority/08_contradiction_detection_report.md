# Contradiction Detection Report

**Authority document set:** `docs/authority/`  
**This document:** `contradiction_detection_report.md`  
**Generated:** 2026-03-28  
**Status:** BINDING FOR REVIEW PROCESS

## Executive Reality Check

The authority set is now aligned to a frozen-engine phase that can close truthfully.

The major contradiction that previously made the phase unfinishable has been resolved:

- engine-blocked Watchman, Stage E, post-entry-management, and six-contract requirements no longer remain falsely tagged as THIS PHASE

This report now focuses on:

1. confirming that the amended scope matches the frozen-engine build
2. keeping terminology and boundaries normalized
3. recording any remaining delivery deltas inside the amended scope

## Resolved Contradictions Register

| ID | Conflict | Resolution | Canonical Rule |
|---|---|---|---|
| CD-01 | Pre-market / Watchman was first deferred, then required | Resolved earlier and retained | Pre-market brief and Watchman gating remain in scope for the phase. |
| CD-02 | Bounded target looked narrower than later requirements | Resolved by amendment | The phase is bounded to the commissionable frozen-engine console, not to engine reopening. |
| CD-03 | Six-contract phase closure was required even though the engine freeze blocked truthful completion | Resolved by amendment | ES, ZN, and CL are the supported preserved profiles for this phase; NQ, 6E, and MGC are deferred. |
| CD-04 | Broader Watchman generation/scoring was marked THIS PHASE even though no frozen-engine path could satisfy it | Resolved by amendment | This phase includes only the target-owned app-surface Watchman validator and hard gate. |
| CD-05 | Full Stage E audit-schema completeness was marked THIS PHASE even though the frozen engine writer does not emit that shape | Resolved by amendment | This phase accepts the frozen engine writer plus target-owned JSONL-backed Run History / Audit Replay surfaces. |
| CD-06 | Engine-authored `post_entry_management` was required even though the frozen engine schemas do not expose it | Resolved by amendment | Engine-authored `post_entry_management` is deferred. |
| CD-07 | "Console" was used ambiguously | Resolved and retained | Terms remain locked: Engine, App surface / operator workspace, Console. |

## Structural Contradiction Checks

### Check 1 - Does the phase definition match the amended THIS PHASE items?

**Assessment:** Clean. The phase definition now matches the actual frozen-engine commissioning target.

### Check 2 - Does the support matrix match the phase scope contract?

**Assessment:** Clean. ES, ZN, and CL are required; NQ, 6E, and MGC are deferred and blocked truthfully.

### Check 3 - Does the acceptance matrix test only the amended phase target?

**Assessment:** Clean. Acceptance now proves the bounded operator console, not impossible engine-owned outputs.

### Check 4 - Does the deferred register capture the previously impossible engine-blocked work?

**Assessment:** Clean. The deferred register now holds the engine-blocked Watchman, Stage E, post-entry-management, and future-contract items.

### Check 5 - Is anything still tagged THIS PHASE that would require reopening `ntb_engine`?

**Assessment:** Clean. The amended THIS PHASE scope is finishable under the engine freeze.

## Normalization Actions

### ND-01 - Terminology stays locked

All docs must use:

- Engine
- App surface / operator workspace
- Console

### ND-02 - Baseline remains descriptive only

The baseline still records what exists. It does not redefine the amended scope.

### ND-03 - Deferred does not mean secretly in progress

Engine-blocked items moved to the deferred register may not reappear in target code as partial stand-ins, shadow systems, or presentation-only claims.

## Implementation Deltas, Not Contradictions

| ID | Current-State Finding | Authority Requirement | Classification |
|---|---|---|---|
| ID-01 | ES, ZN, and CL are operational preserved profiles | Required preserved profiles are commissionable in this phase | Delivery target |
| ID-02 | NQ, 6E, and MGC remain blocked | Deferred contracts must stay blocked and be surfaced truthfully | Boundary enforcement |
| ID-03 | Recent-session evidence, Run History, and Audit / Replay are real and local | Evidence/history must remain truthful and fail-closed | Delivery target |
| ID-04 | Manual verification items are still outstanding | Operator sign-off is still required for phase closure | Acceptance follow-through |

## Review Loop Use

Run this report before any serious implementation cycle and whenever the authority set is amended again.

The contradiction review is complete only when:

1. no THIS PHASE item requires reopening `ntb_engine`
2. no support-matrix item conflicts with the current phase contract
3. the acceptance matrix still proves the amended phase honestly
4. the baseline still distinguishes authority from current code reality

## Final Canonical Position

The active target is a bounded Marimo app surface that truthfully commissions the preserved engine for ES, ZN, and CL, enforces a validator-driven Watchman gate with `mo.stop()`, reads real local JSONL-backed operator evidence, and remains fail-closed under the engine freeze.
