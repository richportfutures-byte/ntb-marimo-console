# Merge Changelog

**Package:** `ntb_best_of_both_authority_set`  
**Generated:** 2026-03-28

## Original Merge Intent

The merged set was created to be the canonical best-of-both authority set:

- governance-first like the uploaded set
- explicit about source precedence and contradiction handling
- no extra binding document count unless clearly necessary

## 2026-03-28 Finishability Amendment

After the frozen-engine blocker review, the authority set was amended to make the current phase truthfully finishable and commissionable without touching `source/ntb_engine`.

### Scope Changes

- retained the bounded Marimo operator console as the phase target
- retained the permanent engine freeze for this phase
- retained the real target-owned wins already completed:
  - JSONL-backed Run History / Audit Replay for preserved profiles
  - validator-driven app-surface Watchman gate with `mo.stop()`
  - fail-closed blocked behavior
  - no raw-status bypass

### Requirements Removed From THIS PHASE

- all-six-contract closure
- broader engine-owned Watchman brief generation/scoring system
- N1-N6 narrative-rule model
- five `WatchmanScores`
- `overall_market_readiness`
- per-contract Watchman prompt templates for brief generation
- Thesis Registry shared with Stage B and drift-proofing
- engine-authored `post_entry_management`
- Stage D protection against `post_entry_management` widening risk
- full Stage E audit schema expansion beyond the frozen engine writer
- real-provider macro/event ingestion as a phase-closing requirement

### Deferred Instead Of Dropped

Those removed items were not rejected as bad ideas. They were reclassified as deferred because they are engine-blocked or otherwise incompatible with the frozen-engine commissioning phase.

### New Phase Closure Interpretation

Phase closure now means:

- supported preserved profiles are ES, ZN, and CL
- blocked contracts remain blocked truthfully
- the app-surface Watchman gate is real and validator-driven
- run history, audit replay, and recent-session evidence are truthful and local
- Windows bootstrap, launch, and acceptance are reproducible

## Package Intent After Amendment

The authority set is now intended to be:

- internally consistent under the frozen-engine architecture
- finishable without reopening `ntb_engine`
- explicit about what is commissionable now versus deferred to a future engine-enabled phase

## 2026-03-28 Acceptance Harness Hardening

The single-entry Windows acceptance harness was tightened so it now directly executes:

- the validator-driven Watchman gate regression slice
- the JSONL-backed Run History / Audit Replay regression slice
- the retained-evidence regression slice

This closes the gap between the amended acceptance matrix and the actual one-command acceptance path.

## 2026-05-06 R00 Authority Contract Universe Reset

The authority set was amended to reset the final product contract universe.

### Scope Changes

- replaced the stale ES/ZN/CL final-target framing
- established the final target support universe as:
  - `ES`
  - `NQ`
  - `CL`
  - `6E`
  - `MGC`
- classified `ZN` as excluded/historical rather than final target support
- classified `GC` as excluded
- stated that `MGC` is the gold contract for this application and that `GC` must not be used as a synonym for `MGC`
- reclassified `NQ`, `6E`, and `MGC` as required onboarding targets rather than generic deferred/non-target contracts

### Explicit Non-Implementation Boundary

R00 is documentation/authority reset only. It does not implement runtime profile changes, Schwab adapter changes, stream manager behavior, broker/order/execution/account/fill/P&L behavior, or engine changes.

### Doctrine Retained

The reset retains:

- engine as sole decision authority
- pre-market brief is not a signal
- manual-only trade execution
- fail-closed behavior
- no fixture fallback after live failure
- 15-second minimum refresh floor

## 2026-05-06 R02 Final Contract Universe Guards

The target project added executable final-contract policy without changing engine schema, runtime profiles, Schwab adapters, or stream behavior.

### Scope Changes

- added a target-owned final contract universe module
- encoded final target contracts as `ES`, `NQ`, `CL`, `6E`, and `MGC`
- encoded `ZN` as legacy/historical and excluded from final target operator selector surfaces
- encoded `GC` as never-supported/excluded
- preserved `preserved_zn_phase1` as a direct legacy runtime profile
- kept `MGC` as the only gold final target contract with no `GC` aliasing

### Explicit Non-Implementation Boundary

R02 does not onboard `NQ`, `6E`, or `MGC`; does not implement streaming; does not modify `source/ntb_engine`; and does not change Schwab adapter behavior.

## 2026-05-06 R03 Stream Manager Foundation

The target project added a fixture-tested Schwab stream manager foundation under `market_data/` without changing default launch behavior, engine code, Schwab adapter code, or runtime profiles.

### Scope Changes

- added explicit stream manager config, lifecycle states, event types, cache snapshots, and client protocol
- kept default stream startup non-live and disabled
- required explicit live opt-in before any injected client login can be attempted
- modeled Marimo refresh as cache reads only
- added idempotent start behavior so an active manager does not open a second login/subscription
- added fail-closed handling for login failure, subscription failure, stale heartbeat, malformed data, symbol mismatch, missing data, and excluded contracts
- added redaction for public stream events, summaries, snapshots, and errors

### Explicit Non-Implementation Boundary

R03 does not implement real Schwab WebSocket networking, does not require credentials for CI/default tests, does not add broker/order/execution/account/fill/P&L behavior, does not onboard `NQ`, `6E`, or `MGC` runtime profiles, and does not re-promote `ZN` or `GC`.

## 2026-05-06 R04 Live Observable Snapshot v2

The target project added a fixture-tested Live Observable Snapshot v2 contract under `live_observables/` without changing launch behavior, engine code, Schwab adapter code, runtime profiles, query authorization, or UI wiring.

### Scope Changes

- added a deterministic JSON-serializable `live_observable_snapshot_v2` schema
- builds from R03 stream-cache snapshots only
- emits primary contract rows for `ES`, `NQ`, `CL`, `6E`, and `MGC`
- keeps `ZN` and `GC` out of the primary contract map
- labels `MGC` as Micro Gold where label metadata is present and does not alias it to `GC`
- computes required-field quality, freshness, symbol matching, mid, and spread ticks
- keeps 5-minute bar fields, trigger distance, range expansion, and volume velocity null for R04
- propagates provider/cache/symbol/field/timestamp blocking reasons fail-closed

### Explicit Non-Implementation Boundary

R04 does not implement real Schwab networking, `CHART_FUTURES` bar aggregation, trigger-state engine states, pipeline query enablement, broker/order/execution/account/fill/P&L behavior, or runtime profile onboarding for `NQ`, `6E`, or `MGC`.

## 2026-05-06 R05 CHART_FUTURES Bar Builder Foundation

The target project added a fixture-tested CHART_FUTURES bar builder foundation under `market_data/` without changing launch behavior, engine code, Schwab adapter code, runtime profiles, trigger-state authorization, query authorization, or UI wiring.

### Scope Changes

- added deterministic one-minute bar, five-minute completed bar, building five-minute bar, per-contract state, ingestion result, and quality contracts
- validates fixture-normalized CHART_FUTURES-style messages for contract, symbol, timestamp, OHLCV, completion flag, and basic OHLC coherence
- rejects or blocks `ZN`, `GC`, malformed records, symbol mismatches, gaps, stale bar state, and out-of-order input
- aggregates completed one-minute bars into five-minute bars only when all five bars for the bucket are present
- keeps partial/building five-minute bars separate from completed confirmation
- adds bar-fact helpers for completed close counts, latest close relation, basic range state, and volume velocity from completed bars only

### Explicit Non-Implementation Boundary

R05 does not implement real Schwab WebSocket networking, trigger-state engine states, pipeline query enablement, broker/order/execution/account/fill/P&L behavior, UI redesign, or runtime profile onboarding for `NQ`, `6E`, or `MGC`.
