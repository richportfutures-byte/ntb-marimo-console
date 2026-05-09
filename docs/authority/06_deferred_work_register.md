# Deferred Work Register

**Authority document set:** `docs/authority/`  
**This document:** `deferred_work_register.md`  
**Generated:** 2026-03-28  
**Status:** BINDING

## Required Final-Target Roadmap Work

These items are not generic deferred extras. They are required work for final product completion after R00 authorizes implementation scope.

| Item | Tag | Source | Prerequisite for Implementation |
|---|---|---|---|
| Promote `NQ` to app-profile-supported final target status | REQUIRED ONBOARDING | R00 support-matrix reset | Future runtime/profile/live-gating roadmap step |
| Promote `6E` to app-profile-supported final target status | REQUIRED ONBOARDING | R00 support-matrix reset | Future runtime/profile/live-gating roadmap step |
| Promote `MGC` to app-profile-supported final target status | REQUIRED ONBOARDING | R00 support-matrix reset | Future runtime/profile/live-gating roadmap step |
| Remaining live workstation upgrades for current `ES` support after the R06 read-model foundation | REQUIRED ONBOARDING | R00 support-matrix reset and R06 foundation | Future Schwab-backed live workstation startup/wiring step |
| Live workstation upgrades for current `CL` support | REQUIRED ONBOARDING | R00 support-matrix reset | Future Schwab-backed live workstation step |
| `ZN` exclusion cleanup | REQUIRED SCOPE CLEANUP | R00 support-matrix reset | Future cleanup step; do not delete engine code or fixtures in R00 |
| `GC` exclusion guard | REQUIRED SCOPE CLEANUP | R00 support-matrix reset | Future guard/test step; `GC` must not become supported or alias `MGC` |

## Deferred Items

| Item | Tag | Source | Prerequisite for Promotion |
|---|---|---|---|
| Full engine-owned Watchman brief generation run | DEFERRED | Layer 2 finishability amendment | Engine reopened by authority amendment |
| Per-contract Watchman prompt templates for brief generation | DEFERRED | Layer 2 finishability amendment | Same as above |
| Watchman Validator narrative rule model N1 through N6 | DEFERRED | Layer 2 finishability amendment | Same as above |
| All five `WatchmanScores` plus `overall_market_readiness` | DEFERRED | Layer 2 finishability amendment | Same as above |
| Thesis Registry shared with Stage B and drift-free proof | DEFERRED | Layer 3 finishability amendment | Engine reopened and shared contract added truthfully |
| Engine-authored `post_entry_management` output | DEFERRED | Layer 7 finishability amendment | Engine reopened and Stage C schema expanded truthfully |
| Stage D protection against `post_entry_management` widening risk when that block becomes real engine output | DEFERRED | D-18 finishability amendment | Same as above |
| Full Stage E audit schema with complete packet, all stage outputs, schema versioning, and no null fields | DEFERRED | Layer 9 finishability amendment | Engine writer/schema reopened |
| Real-provider macro/event ingestion beyond the authorized live workstation slice | DEFERRED | Data-truth amendment | New phase or explicit authority amendment |
| Automated JSONL session analytics and cross-session performance attribution | DEFERRED | Prior deferred register | Current bounded console accepted in real use with sufficient real-session volume |
| Direct NinjaTrader platform integration to eliminate manual packet assembly | DEFERRED | Prior deferred register | Same as above |
| Multi-session regime tracking that conditions Stage B on recent decision history | DEFERRED | Prior deferred register | Same as above plus sufficient real-session evidence |
| Deferred-item promotion rules | DEFERRED | Prior deferred register | Current phase accepted and future-phase scope formally opened |
| Next-phase starting point after R00 | UNKNOWN | R00 authority reset | Not decided with enough conviction to bind now |

## Promotion Gate

Before any DEFERRED item is promoted, all of the following must be true:

1. the active authority set explicitly opens the work
2. the engine boundary decision is revisited explicitly through authority amendment if the item depends on `ntb_engine`
3. the item is reclassified against the updated authority set before implementation begins
4. no target-side stand-in is used to impersonate engine-owned decision authority

Before any REQUIRED ONBOARDING or REQUIRED SCOPE CLEANUP item is implemented, the future roadmap step must define its implementation boundary, tests, and migration risk.

## Rejected Items

| Item | Rejection Reason |
|---|---|
| `ZN` final target support | The final target universe is `ES`, `NQ`, `CL`, `6E`, and `MGC`; `ZN` is excluded/historical |
| `GC` support or `GC` aliasing for `MGC` | `MGC` is the gold contract for this application; `GC` is excluded |
| Cross-contract matrix | Pulls the product away from disciplined contract-specific gating into comparative dashboard synthesis and weakens auditability |
| Confidence score as progress bar or sentiment indicator | Trains the operator to read sentiment instead of structure |
| Auto-retry logic that resubmits a rejected packet with relaxed thresholds | Gate bypass disguised as convenience |
| Suggested-trade output on `NO_TRADE` | Undermines the failed gate by offering a second bite at the decision |

## Rejected Items Protocol

A REJECTED item may be reconsidered only in a future product cycle through formal re-interrogation. It may not:

- appear in code as a disabled feature
- reappear in planning as a likely addition
- be implemented partially under a new name
- be proposed informally as exploration

## Vision Cross-References

| Item | Source | Full Record |
|---|---|---|
| Engine change policy | C3 | `product_authority_brief.md` |
| Permanent anti-misinterpretation doctrine | L5 | `product_authority_brief.md` |
