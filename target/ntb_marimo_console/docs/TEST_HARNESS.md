# E1 Release-Candidate Test Harness

The canonical local verification command is:

```bash
PYTHONPATH="src:../../source/ntb_engine/src:." uv run python scripts/verify_release_candidate.py
```

Use list mode to inspect the exact bounded pytest slices without running them:

```bash
PYTHONPATH="src:../../source/ntb_engine/src:." uv run python scripts/verify_release_candidate.py --list
```

## Scope

This harness is the project-owned E1 release-candidate safety net for deterministic, non-live verification. It consolidates the R17 non-live acceptance coverage with the later cockpit evidence, D2 dry-run, and D3 partial/fail-closed release-record checks. It checks:

- Final contract universe integrity for `ES`, `NQ`, `CL`, `6E`, and `MGC`.
- Excluded-contract enforcement for `ZN` and `GC`.
- Runtime profile registry behavior.
- Live observable schema, stream manager/cache behavior, and CHART_FUTURES bar-builder blocking semantics.
- Fail-closed trigger/query behavior.
- Pipeline query-gate provenance.
- Operator cockpit rendering and blocked-state display.
- Fixture-safe, non-live default launch behavior.
- No live credential dependency for default verification.
- No fixture fallback after live failure behavior.
- Audit/replay/performance-review determinism.
- Cockpit event evidence and trigger transition replay attribution.
- Redaction and sensitive-value exclusion.
- D2 dry-run rehearsal boundaries.
- The D3 live rehearsal record as `PARTIAL / FAIL-CLOSED`.
- Absence of broker/order/account/fill/P&L behavior in the covered foundations.
- No default-live launch behavior.

## Non-live guarantees

Default verification is non-live. Schwab credentials are not required. The harness does not read `.state/secrets/schwab_live.env`, token state, streamer URLs, customer IDs, correl IDs, account IDs, or authorization payloads.

The harness does not run live Schwab probes, OAuth preparation, streamer login probes, token refresh probes, or manual live rehearsal scripts.

## What this does not prove

This harness does not prove broker execution, order placement, account state, fills, P&L, trading edge, expectancy validity, or production live Schwab readiness. It does not authorize trades. E1 is a release-candidate fixture-safety check, not a trading edge validator.

The recorded D3 live rehearsal is partial: login and five-contract subscription plumbing reached the reported live path, but `market_data_received=no` and `received_contracts_count=0`. That result must remain fail-closed and does not prove LEVELONE_FUTURES delivery, CHART_FUTURES delivery, or production live workstation readiness.

Live/manual rehearsal remains separate and must stay explicitly opt-in.

## Hosted CI

No hosted CI workflow is added by E1. The repository currently has no established workflow convention, so local fixture-only verification is the canonical foundation.
