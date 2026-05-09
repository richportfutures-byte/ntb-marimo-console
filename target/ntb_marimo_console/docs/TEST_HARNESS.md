# R17 Non-Live Acceptance Harness

The canonical local verification command is:

```bash
PYTHONPATH=src python3 scripts/verify_non_live_acceptance.py
```

Use list mode to inspect the exact bounded pytest slices without running them:

```bash
PYTHONPATH=src python3 scripts/verify_non_live_acceptance.py --list
```

## Scope

This harness is the project-owned R17 safety net for deterministic, non-live verification. It checks:

- Final contract universe integrity for `ES`, `NQ`, `CL`, `6E`, and `MGC`.
- Excluded-contract enforcement for `ZN` and `GC`.
- Fail-closed trigger/query behavior.
- Fixture-safe, non-live default launch behavior.
- No live credential dependency for default verification.
- No fixture fallback after live failure behavior.
- Audit/replay/performance-review determinism.
- Absence of broker/order/account/fill/P&L behavior in the covered foundations.
- No default-live launch behavior.

## Non-live guarantees

Default verification is non-live. Schwab credentials are not required. The harness does not read `.state/secrets/schwab_live.env`, token state, streamer URLs, customer IDs, correl IDs, account IDs, or authorization payloads.

The harness does not run live Schwab probes, OAuth preparation, streamer login probes, token refresh probes, or manual live rehearsal scripts.

## What this does not prove

This harness does not prove broker execution, order placement, account state, fills, P&L, trading edge, expectancy validity, or live operational readiness. It does not authorize trades. R17 is a safety net, not a trading edge validator.

Live/manual rehearsal remains a separate R18 concern and must stay explicitly opt-in.

## Hosted CI

No hosted CI workflow is added by R17. The repository currently has no established workflow convention, so local fixture-only verification is the canonical foundation.
