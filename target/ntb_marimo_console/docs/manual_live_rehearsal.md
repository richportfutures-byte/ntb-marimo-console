# R18 Manual Live Rehearsal

R18 adds an explicit, operator-run manual live rehearsal foundation. It does not change default app launch, fixture mode, or the canonical non-live harness.

## Safe fixture/dry-run command

Run from `target/ntb_marimo_console`:

```bash
PYTHONPATH=src python3 scripts/run_manual_live_rehearsal.py --fixture
```

Equivalent dry-run alias:

```bash
PYTHONPATH=src python3 scripts/run_manual_live_rehearsal.py --dry-run
```

Additional fixture scenarios:

```bash
PYTHONPATH=src python3 scripts/run_manual_live_rehearsal.py --dry-run --fixture-scenario missing
PYTHONPATH=src python3 scripts/run_manual_live_rehearsal.py --dry-run --fixture-scenario stale
PYTHONPATH=src python3 scripts/run_manual_live_rehearsal.py --dry-run --fixture-scenario mismatch
PYTHONPATH=src python3 scripts/run_manual_live_rehearsal.py --dry-run --fixture-scenario live_failure
```

Fixture mode uses mocked clients only. It requires no Schwab credentials and is safe for local default testing.

## Explicit manual live checklist command

Run from `target/ntb_marimo_console`:

```bash
PYTHONPATH=src python3 scripts/run_manual_live_rehearsal.py --live
```

This command prints the manual live checklist and exits with a manual-required status. It is not part of default tests and is not part of the canonical non-live harness.

The existing single-quote Schwab live harness remains the concrete opt-in market-data smoke path documented in `docs/schwab_manual_live_harness_runbook.md`. R18 does not replace it or make it part of CI.

## What the rehearsal covers

The fixture-verifiable rehearsal covers:

- Final target universe: `ES`, `NQ`, `CL`, `6E`, `MGC`.
- Excluded contracts: `ZN`, `GC` remain blocked and are not rehearsed as supported.
- `LEVELONE_FUTURES` quote update assumptions.
- `CHART_FUTURES` one-minute and five-minute bar update assumptions.
- One stream connection discipline.
- No repeated login during repeated cache/UI refresh reads.
- Cache-readable state for Marimo/operator workspace assumptions.
- Missing, stale, and mismatched data fail closed.
- No false `QUERY_READY` without deterministic trigger/query-gate prerequisites.
- No fixture fallback after simulated live failure.
- Evidence JSONL serializability for rehearsal events through the R15 evidence layer.

## Manual observations required for live rehearsal

An operator must manually confirm:

- One approved live rehearsal window is active.
- One session login and one subscription cycle occurs.
- `LEVELONE_FUTURES` updates are observed for `ES`, `NQ`, `CL`, `6E`, and `MGC`.
- `CHART_FUTURES` updates are observed for `ES`, `NQ`, `CL`, `6E`, and `MGC`.
- Repeated UI/cache refresh reads do not create repeated Schwab logins.
- Stale, missing, delayed, or mismatched data keeps readiness blocked.
- Live data alone does not approve trades, reject trades, size trades, rewrite Stage B, create setup alternatives after `NO_TRADE`, or create `QUERY_READY`.

## Redacted output

Harness output may include contract symbols and high-level states. It must not include raw credentials, token contents, authorization headers, app keys, secrets, token JSON, streamer URLs, customer IDs, correl IDs, account IDs, or authorization payloads.

Do not paste raw live payloads into issue reports.

## What this does not prove

R18 does not prove production readiness, broker execution, order routing, account state, fills, P&L, trading edge, expectancy, or Schwab uptime. It does not authorize trades and does not introduce a second decision authority outside the preserved engine.

## CI and defaults

The canonical CI/default-safe command remains:

```bash
PYTHONPATH=src python3 scripts/verify_non_live_acceptance.py
```

The manual live rehearsal is explicitly opt-in and is excluded from the non-live acceptance harness.
