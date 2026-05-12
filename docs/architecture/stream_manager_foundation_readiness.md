# Stream Manager Foundation Readiness

Checkpoint: `ee522c2 Add Schwab stream manager foundation`

## Decision

R03 Stream Manager Foundation is ready to advance to R04 Live Observable Snapshot v2.

No second broad R03 implementation slice is justified at this checkpoint. The current target-owned stream manager/cache boundary is sufficient for R04 to consume stream/cache snapshots and enrich normalized observable contracts without changing launch behavior or live-safety boundaries.

## Verified Boundary

- Default stream manager configuration is non-live and disabled.
- Explicit live opt-in is required before login.
- `manager.start()` remains the single boundary that performs login and subscription.
- Starting an already-active manager is idempotent and does not repeat login or subscription.
- Marimo-style reads are cache-first and do not call `start()`, `login()`, or `subscribe()`.
- Stream manager snapshots expose subscription request/result state.
- Heartbeat age metadata is visible, and stale heartbeat state fails closed.
- Login, subscription, cache, and exception surfaces are redacted before snapshot/public output.
- Excluded contracts block before login.
- Final target universe remains `ES`, `NQ`, `CL`, `6E`, `MGC`.
- `ZN` and `GC` remain excluded.
- Stream manager output is not wired into query approval; query approval remains governed by existing trigger-state rules.

## Runtime Boundary

- The operator live launcher starts the manager only under explicit `OPERATOR_LIVE_RUNTIME` opt-in.
- Runtime producers read an existing manager snapshot and do not call `start()`, `login()`, or `subscribe()` from refresh/read paths.
- Schwab session `login`, `subscribe`, `dispatch_one`, and `close` boundaries are explicit.
- Receive dispatch is operator-driven and is not called by default import, CI, renderer, readiness, or refresh paths.

## R04 Boundary

R04 should consume stream/cache snapshots and enrich normalized observable contracts.

R04 should not rework Schwab auth, add broker/order/execution/account/fill/P&L behavior, make default launch live, add `CHART_FUTURES` bar building, wire stream output into query approval, re-promote `ZN`, add or alias `GC`, or treat `MGC` as `GC`.

## Remaining Known Gaps

- Full live workstation is incomplete.
- Live Observable Snapshot v2 completion.
- `CHART_FUTURES` bar builder.
- ES/CL live workstation upgrades.
- NQ/6E/MGC runtime/profile/live-gating onboarding.
- Manual live rehearsal.
- Release candidate hardening.

## Verification

Command:

```bash
uv run pytest -q target/ntb_marimo_console/tests/test_schwab_stream_manager_foundation.py target/ntb_marimo_console/tests/test_operator_live_launcher.py target/ntb_marimo_console/tests/test_schwab_stream_client.py target/ntb_marimo_console/tests/test_schwab_streamer_session.py target/ntb_marimo_console/tests/test_live_observable_snapshot_v2.py target/ntb_marimo_console/tests/test_operator_live_runtime.py
```

Result: passed at this checkpoint.

`git diff --check`: passed.
