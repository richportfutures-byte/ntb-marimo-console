# Current State Baseline

**Authority document set:** `docs/authority/`  
**This document:** `current_state_baseline.md`  
**Generated:** 2026-03-28  
**Status:** INFORMATIONAL

> [!WARNING]
> This document describes what exists today. It is not a requirements document. Requirements are defined by `current_phase_scope_contract.md`. If this document conflicts with verified code, the code is the ground truth and this document must be updated.

## What the Code Does Today

### Runtime Profiles and Support Boundary

- `fixture_es_demo`: available as a fixture/demo runtime path
- `preserved_es_phase1`: operational
- `preserved_zn_phase1`: operational
- `preserved_cl_phase1`: operational
- `NQ`, `6E`, and `MGC`: blocked and surfaced as blocked candidates with concrete reason categories

### Windows Runtime Ownership

- target bootstrap/setup on Windows is reproducible
- direct launch uses a target-owned Marimo runtime path under `target/ntb_marimo_console/.state/marimo`
- direct launch no longer depends on the denied host-level Marimo config path
- a single-entry Windows acceptance harness exists and now runs dedicated regression slices for the Watchman gate, JSONL-backed Run History / Audit Replay, and retained evidence

### Watchman and Pre-Market Layer

- supported preserved profiles render target-owned pre-market briefs
- a target-owned Watchman validator exists for the app surface
- `mo.stop()` is wired to Validator output in the real Marimo entry path
- raw brief `status` does not authorize the gate
- broader engine-owned Watchman brief/scoring generation is not implemented in target code and is now deferred rather than required in this phase

### Preserved Engine Execution Path

- preserved ES, ZN, and CL profiles can execute the bounded preserved-engine query path
- profile switching across ES, ZN, and CL is implemented and fail-closed
- stale per-profile session state is cleared on successful switch

### Run History, Audit Replay, and Recent Session Evidence

- preserved-profile Run History reads real local JSONL-backed rows
- preserved-profile Audit / Replay reads from real local JSONL-backed records and blocks if missing
- recent-session evidence is durable across app restarts
- retained recent-session evidence can be cleared explicitly
- current-session evidence and restored-prior-run evidence remain distinct in the UI

### Primary App Surface

- startup, workflow, profile, and evidence surfaces render readably
- supported profiles and blocked candidates are surfaced readably
- raw JSON remains confined to secondary/debug surfaces

### Tests and Acceptance

- target regression and acceptance coverage exists for:
  - supported profile listing
  - blocked candidate audit
  - supported-profile preflight
  - validator-driven `mo.stop()` gate behavior
  - JSONL-backed run history / audit replay
  - recent-session evidence persistence and clear behavior
  - direct launch-path coherence on Windows

## What the Amended Phase Requires That Is Confirmed Not Yet Done

| Item | Status |
|---|---|
| Manual verification items in `acceptance_matrix.md` | Not yet confirmed by operator |
| Final release-candidate acceptance run from a clean workspace | Requires execution at sign-off time |

## Docs vs Code Delta

| Documentation State | Actual Code State | Resolution |
|---|---|---|
| Earlier authority set required full engine-owned Watchman generation/scoring in this phase | Target code implements only the app-surface Watchman gate truthfully | Requirement amended and broader Watchman work deferred |
| Earlier authority set required six-contract phase closure | ES, ZN, and CL are commissionable; NQ, 6E, and MGC remain blocked | Support matrix amended to match the commissionable frozen-engine scope |
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

1. a supported preserved profile regresses or a new one is truly added under a future amendment
2. an acceptance item is confirmed complete
3. the amended phase closes
4. a future authority amendment changes the commissionable boundary again

Do not update this document to reflect aspiration. Every entry must remain factual and verifiable.
