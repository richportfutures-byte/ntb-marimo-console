# Acceptance Matrix

**Authority document set:** `docs/authority/`  
**This document:** `acceptance_matrix.md`  
**Generated:** 2026-03-28  
**Status:** BINDING

## Enumerated Acceptance Tests

All tests are binary pass/fail. All must pass in CI or in the documented Windows acceptance run with no live LLM dependency.

### Windows Bootstrap and Runtime Ownership

| Test ID | Condition | Expected Result | Pass Criteria |
|---|---|---|---|
| WIN-1 | Target bootstrap command executed from `target/ntb_marimo_console` | Completes cleanly | `.venv` created and target imports succeed |
| WIN-2 | Direct Marimo launch command executed for a supported preserved profile | Starts with target-owned Marimo runtime path | No host config-path permission warning; localhost becomes reachable |
| WIN-3 | Target-owned Marimo runtime path cannot be prepared | Launch fails closed | Readable failure; no silent fallback to host-level Marimo config path |

### Supported Profiles and Blocked Candidates

| Test ID | Condition | Expected Result | Pass Criteria |
|---|---|---|---|
| SP-1 | Supported profile list command runs | Supported profiles are listed | `fixture_es_demo`, `preserved_es_phase1`, `preserved_zn_phase1`, `preserved_cl_phase1` present |
| SP-2 | Preserved-contract eligibility audit runs | Deferred contracts are reported truthfully | `NQ`, `6E`, and `MGC` remain blocked with named reason categories |
| SP-3 | Strict preflight runs for `preserved_es_phase1`, `preserved_zn_phase1`, and `preserved_cl_phase1` | Preflight passes | Each supported preserved profile reports PASS |

### Watchman Gate

| Test ID | Condition | Expected Result | Pass Criteria |
|---|---|---|---|
| WG-1 | Brief missing narrative substance | `NEEDS_REVIEW`, `mo.stop()` fires, downstream pipeline surface blocked | Specific failing validator named |
| WG-2 | Raw brief or contract status set directly | `mo.stop()` still fires | Gate reads Validator output only |
| WG-3 | Brief is validator-authorized | Gate opens | Pipeline action becomes available only when Validator status is `READY` |

### Supported-Profile Operations

| Test ID | Condition | Expected Result | Pass Criteria |
|---|---|---|---|
| OP-1 | Supported profiles rendered in app surface | Operator sees supported and blocked states readably | Supported profiles and blocked candidates appear without raw JSON |
| OP-2 | Supported profile switch `ES -> ZN`, `ZN -> CL`, `CL -> ES` | Switch completes cleanly | Active profile updates and stale session state is cleared |
| OP-3 | Switch to blocked or unsupported profile | Fails closed | Readable blocked diagnostic; active supported profile remains intact |

### Run History and Audit Replay

| Test ID | Condition | Expected Result | Pass Criteria |
|---|---|---|---|
| RH-1 | Supported preserved profile completes bounded query execution | Run History reads real local JSONL-backed rows | Rows come from local JSONL, not fixture placeholders |
| RH-2 | Supported preserved profile has a qualifying local JSONL record | Audit / Replay is available | Replay derives from the real local JSONL-backed record |
| RH-3 | Supported preserved profile has no qualifying local JSONL record | Audit / Replay remains blocked | No synthetic replay record is shown |
| RH-4 | Attempt to clear or reset preserved-engine JSONL run history from the app surface | Operation blocked | No destructive target-side clear path exists |

### Recent Session Evidence

| Test ID | Condition | Expected Result | Pass Criteria |
|---|---|---|---|
| EV-1 | App restarted after a supported-profile session | Recent-session evidence restores | Restored prior-run evidence is visible and attributable |
| EV-2 | Profile switch followed by restart | Attribution remains correct | No cross-profile bleed between ES, ZN, and CL |
| EV-3 | Operator clears retained recent-session evidence intentionally | Retained evidence is removed | Restored prior-run evidence is empty on next launch until new evidence is written |
| EV-4 | Retained-evidence persistence fails or restore file is corrupt | Fail closed | Readable restore/persistence status; no fake green state |

### Primary Surface Readability

| Test ID | Condition | Expected Result | Pass Criteria |
|---|---|---|---|
| UI-1 | App renders in normal operator mode | Primary surfaces remain readable | No raw JSON in pre-market, workflow, profile, or evidence surfaces |
| UI-2 | Debug information is needed | Debug stays secondary | Machine-detail output remains in clearly secondary/debug surfaces only |

### Acceptance Harness

| Test ID | Condition | Expected Result | Pass Criteria |
|---|---|---|---|
| AH-1 | Single-entry Windows acceptance command runs | Categorized report produced | Report covers environment/bootstrap, supported profiles, blocked candidates, evidence lifecycle, and launch-path status |
| AH-2 | Any real acceptance check fails | Command fails nonzero | No silent skip and no false PASS |

## Manual Verification Items

| Item | What to Verify | Verified By |
|---|---|---|
| MV-1 | Brief language is actionable against the operator's own platform for ES, ZN, and CL | Operator |
| MV-2 | ES and ZN causal vocabulary remain distinct and CL EIA wording remains specific | Operator |
| MV-3 | Recent-session evidence and JSONL-backed run history are understandable without debug knowledge | Operator |
| MV-4 | Trade execution remains manual only | Operator |

## What Successful Testing Proves

Successful CI and acceptance prove:

- supported preserved profiles launch and preflight correctly
- blocked contracts remain blocked truthfully
- the Watchman gate is validator-driven and fail-closed
- supported-profile switching does not bleed stale state across contracts
- run history and audit replay read real local JSONL-backed records
- recent-session evidence persists across restarts and can be cleared intentionally
- the Windows launch path is owned by the target project and does not depend on host-global Marimo config state

Successful CI and acceptance do **not** prove:

- real-provider macro/event ingestion
- six-contract closure
- full engine-owned Watchman brief/scoring generation
- full Stage E audit-schema completeness beyond the frozen engine writer
- operator performance on unseen live markets

## Build Rejection Even If Tests Pass

A build is rejected if any of the following is true:

1. the Watchman gate reads from a manually assigned status instead of Validator output
2. a blocked contract appears ready or selectable as supported
3. run history or audit replay is still fixture-backed for supported preserved profiles
4. restored recent-session evidence misattributes records across profiles
5. a failing test was made to pass by weakening the assertion instead of fixing the behavior

## Application Failure Conditions

| Failure Mode | Description |
|---|---|
| Silent bad data | System produces confident-looking output on malformed or unsupported state and operator cannot tell |
| Fake READY gate | Watchman shows READY for a brief that never earned it through real validation |
| Unwired gate | `mo.stop()` exists but is not driven by real Validator output |
| Blocked contract leakage | `NQ`, `6E`, or `MGC` appears selectable as if supported |
| Placeholder history | Run History or Audit / Replay shows fixture-backed placeholders instead of real local JSONL-backed records |
| Evidence bleed | Recent-session evidence from one profile appears as if it belongs to another |
| Persistence lie | Restore or write failures are hidden behind a fake healthy status |
| Host-path dependence | App launch depends on a denied or unwritable host-level Marimo config path |
