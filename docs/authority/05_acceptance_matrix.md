# Acceptance Matrix

**Authority document set:** `docs/authority/`  
**This document:** `acceptance_matrix.md`  
**Generated:** 2026-03-28  
**Status:** BINDING

## R00 Authority-Reset Acceptance Tests

All R00 tests are binary pass/fail. R00 is a documentation/authority reset only.

| Test ID | Condition | Expected Result | Pass Criteria |
|---|---|---|---|
| R00-1 | Authority docs describe final target contracts | Final target support is `ES`, `NQ`, `CL`, `6E`, and `MGC` | All five appear as final target contracts in the phase contract and support matrix |
| R00-2 | Authority docs describe excluded contracts | `ZN` and `GC` are excluded from final target support | `ZN` appears only as excluded/historical/current-state legacy; `GC` appears only as excluded |
| R00-3 | Gold contract naming is checked | `MGC` is the gold contract for this application | `MGC` is never mislabeled as `GC`; `GC` is not used as a synonym for `MGC` |
| R00-4 | Onboarding targets are classified truthfully | `NQ`, `6E`, and `MGC` are required onboarding targets | They are not described as engine-missing contracts or generic non-target deferred extras |
| R00-5 | Current runtime profile reality remains factual | Current profiles are fixture `ES`, preserved `ES`, preserved `ZN`, and preserved `CL` | Authority baseline distinguishes current runtime profiles from final target support |
| R00-6 | Runtime implementation is not claimed complete | Live networking, startup wiring, and authorization work remains future roadmap work | No R00 doc claims final live Schwab workstation implementation is complete |
| R00-7 | Doctrine remains intact | Engine decision authority, manual-only execution, and fail-closed behavior remain binding | No authority doc adds broker/order/execution/account/fill/P&L behavior or weakens fail-closed language |

## Current-State Runtime Acceptance Preserved As Factual Baseline

The following checks remain truthful for the current implementation and may be used as targeted regression slices. They do not define final target support.

### Windows Bootstrap and Runtime Ownership

| Test ID | Condition | Expected Result | Pass Criteria |
|---|---|---|---|
| WIN-1 | Target bootstrap command executed from `target/ntb_marimo_console` | Completes cleanly | `.venv` created and target imports succeed |
| WIN-2 | Direct Marimo launch command executed for a current supported preserved profile | Starts with target-owned Marimo runtime path | No host config-path permission warning; localhost becomes reachable |
| WIN-3 | Target-owned Marimo runtime path cannot be prepared | Launch fails closed | Readable failure; no silent fallback to host-level Marimo config path |

### Current Runtime Profiles and Onboarding Candidates

| Test ID | Condition | Expected Result | Pass Criteria |
|---|---|---|---|
| SP-1 | Supported profile list command runs | Current runtime profiles are listed | `fixture_es_demo`, `preserved_es_phase1`, `preserved_nq_phase1`, `preserved_6e_phase1`, `preserved_mgc_phase1`, `preserved_zn_phase1`, and `preserved_cl_phase1` present |
| SP-2 | Preserved-contract eligibility audit runs | App-profile gaps are reported truthfully | No remaining final-target onboarding candidate is reported as blocked |
| SP-3 | Strict preflight runs for current preserved profiles | Preflight passes for current supported preserved profiles | `preserved_es_phase1`, `preserved_nq_phase1`, `preserved_6e_phase1`, `preserved_mgc_phase1`, `preserved_zn_phase1`, and `preserved_cl_phase1` report PASS as current-state profiles |

### Watchman Gate

| Test ID | Condition | Expected Result | Pass Criteria |
|---|---|---|---|
| WG-1 | Brief missing narrative substance | `NEEDS_REVIEW`, `mo.stop()` fires, downstream pipeline surface blocked | Specific failing validator named |
| WG-2 | Raw brief or contract status set directly | `mo.stop()` still fires | Gate reads Validator output only |
| WG-3 | Brief is validator-authorized | Gate opens | Pipeline action becomes available only when Validator status is `READY` |

### Current Supported-Profile Operations

| Test ID | Condition | Expected Result | Pass Criteria |
|---|---|---|---|
| OP-1 | Current profiles rendered in app surface | Operator sees current supported and not-current states readably | Current profiles and onboarding candidates appear without raw JSON |
| OP-2 | Current profile switch `ES -> ZN`, `ZN -> CL`, `CL -> ES` | Switch completes cleanly as current-state behavior | Active profile updates and stale session state is cleared |
| OP-3 | Switch to unsupported profile | Fails closed | Readable blocked diagnostic; active supported profile remains intact |

### Run History and Audit Replay

| Test ID | Condition | Expected Result | Pass Criteria |
|---|---|---|---|
| RH-1 | Current preserved profile completes bounded query execution | Run History reads real local JSONL-backed rows | Rows come from local JSONL, not fixture placeholders |
| RH-2 | Current preserved profile has a qualifying local JSONL record | Audit / Replay is available | Replay derives from the real local JSONL-backed record |
| RH-3 | Current preserved profile has no qualifying local JSONL record | Audit / Replay remains blocked | No synthetic replay record is shown |
| RH-4 | Attempt to clear or reset preserved-engine JSONL run history from the app surface | Operation blocked | No destructive target-side clear path exists |

### Recent Session Evidence

| Test ID | Condition | Expected Result | Pass Criteria |
|---|---|---|---|
| EV-1 | App restarted after a current supported-profile session | Recent-session evidence restores | Restored prior-run evidence is visible and attributable |
| EV-2 | Profile switch followed by restart | Attribution remains correct | No cross-profile bleed between current profiles |
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
| AH-1 | Single-entry Windows acceptance command runs | Categorized report produced | Report covers environment/bootstrap, current profiles, onboarding candidates, evidence lifecycle, and launch-path status |
| AH-2 | Any real acceptance check fails | Command fails nonzero | No silent skip and no false PASS |

## Superseded Runtime Acceptance Assumptions

These assumptions are superseded by R00:

- final target support requires `ZN`
- final target support is bounded to `ES`, `ZN`, and `CL`
- `NQ`, `6E`, and `MGC` are generic deferred/non-target contracts
- current `ZN` runtime support implies final target inclusion
- any prior assumption that `GC` may be treated as shorthand for `MGC`

## Manual Verification Items

| Item | What to Verify | Verified By |
|---|---|---|
| MV-1 | Authority docs identify final target contracts as `ES`, `NQ`, `CL`, `6E`, and `MGC` | Operator |
| MV-2 | `ZN` is classified only as excluded/historical/current-state legacy | Operator |
| MV-3 | `GC` is excluded and is not used as a synonym for `MGC` | Operator |
| MV-4 | Brief language remains actionable against the operator's own platform for current `ES` and `CL` profiles | Operator |
| MV-5 | Recent-session evidence and JSONL-backed run history are understandable without debug knowledge | Operator |
| MV-6 | Trade execution remains manual only | Operator |

## What Successful R00 Testing Proves

Successful R00 verification proves:

- the authority set now binds final target support to `ES`, `NQ`, `CL`, `6E`, and `MGC`
- `ZN` is excluded/historical rather than required final target support
- `GC` is excluded and is not a synonym for `MGC`
- current runtime profile facts are preserved without redefining the final target
- future onboarding work is correctly classified for `NQ`, `6E`, and `MGC`
- engine decision authority, manual-only execution, and fail-closed doctrine remain intact

Successful R00 verification does **not** prove:

- final live Schwab workstation readiness for `NQ`, `6E`, or `MGC`
- final live Schwab workstation readiness
- real-provider macro/event ingestion
- full engine-owned Watchman brief/scoring generation
- full Stage E audit-schema completeness beyond the frozen engine writer
- operator performance on unseen live markets

## Build Rejection Even If Tests Pass

A build is rejected if any of the following is true:

1. the authority docs still define final target support around `ES`, `ZN`, and `CL`
2. `ZN` appears as required final target support rather than excluded/historical
3. `GC` appears as supported or as a synonym for `MGC`
4. `NQ`, `6E`, or `MGC` are treated as engine-missing instead of final target profile foundations
5. R00 claims runtime/profile/live-gating implementation is complete
6. the Watchman gate reads from a manually assigned status instead of Validator output
7. a blocked, excluded, or unsupported contract appears ready or selectable as supported
8. run history or audit replay is fixture-backed while presented as real local JSONL-backed records
9. restored recent-session evidence misattributes records across profiles
10. a failing test was made to pass by weakening the assertion instead of fixing the behavior

## Application Failure Conditions

| Failure Mode | Description |
|---|---|
| Silent bad data | System produces confident-looking output on malformed or unsupported state and operator cannot tell |
| Fake READY gate | Watchman shows READY for a brief that never earned it through real validation |
| Unwired gate | `mo.stop()` exists but is not driven by real Validator output |
| Excluded contract leakage | `ZN` or `GC` appears as final target support |
| Gold contract mislabel | `MGC` is labeled, aliased, or onboarded as `GC` |
| Unsupported contract leakage | A non-final-target or excluded contract appears selectable as current final-target app-profile support |
| Placeholder history | Run History or Audit / Replay shows fixture-backed placeholders instead of real local JSONL-backed records |
| Evidence bleed | Recent-session evidence from one profile appears as if it belongs to another |
| Persistence lie | Restore or write failures are hidden behind a fake healthy status |
| Host-path dependence | App launch depends on a denied or unwritable host-level Marimo config path |
