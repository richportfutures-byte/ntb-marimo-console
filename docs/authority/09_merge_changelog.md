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
