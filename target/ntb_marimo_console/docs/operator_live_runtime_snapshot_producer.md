# Operator Live Runtime Snapshot Producer

R26 wires the operator workstation to an app-owned runtime snapshot producer boundary. The boundary is cache-first: Marimo refreshes read the latest local `StreamManagerSnapshot` or `StreamCacheSnapshot` supplied to the session lifecycle and pass it into the five-contract readiness summary.

## Modes

- `SAFE_NON_LIVE`: default mode. The workstation uses fixture/preserved-shell readiness, labels it as non-live, and does not request Schwab credentials or live network access.
- `OPERATOR_LIVE_RUNTIME`: explicit operator-live mode. The lifecycle reads a runtime/cache snapshot producer and labels readiness as runtime-cache-derived when a snapshot is available.
- `LIVE_RUNTIME_UNAVAILABLE`: live runtime was requested but no producer snapshot exists. The workstation passes a blocking cache snapshot to readiness so it does not fall back to fixtures.
- `LIVE_RUNTIME_STALE`: the supplied producer snapshot is stale and blocks readiness.
- `LIVE_RUNTIME_ERROR`: the supplied producer reports error/blocked/shutdown state, or the producer raises. The error summary is redacted and blocks readiness.
- `LIVE_RUNTIME_DISABLED`: the supplied producer snapshot is disabled and blocks readiness.

## Operator Launch Behavior

Default tests, imports, smoke runs, and safe harnesses remain non-live. Operator-live mode is selected only by explicit operator configuration such as `NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME` or by injecting a producer into `load_session_lifecycle_from_env`.

The Marimo app creates the producer holder once with `mo.state`. Refresh, reload, reset, and bounded-query actions reuse that producer object and read the latest cache/snapshot. Those reads do not call Schwab login, proof-capture scripts, broker/order APIs, account APIs, fill APIs, or P&L code.

The UI refresh path preserves the 15-second minimum refresh floor from `MIN_STREAM_REFRESH_FLOOR_SECONDS`. Runtime-derived readiness is visible in Runtime Identity, Session Lifecycle, and Five-Contract Readiness Summary fields.

## Safety Boundaries

- The final readiness universe remains `ES`, `NQ`, `CL`, `6E`, and `MGC`.
- Excluded final target contracts remain `ZN` and `GC`.
- `MGC` remains Micro Gold and is not mapped to `GC`.
- A missing, stale, disabled, error, unsupported, or excluded runtime snapshot blocks readiness.
- Live/runtime failure does not fall back to fixture readiness.
- Readiness remains a read-only operator visibility surface. The preserved engine remains the only decision authority, and the app still contains no broker/order/account/fill/P&L behavior.

## Remaining Live-Start Blocker

The operator app now has the producer injection path and the lifecycle/readiness wiring. The real Schwab stream-manager start still must be supplied by an explicit operator-live entry point that constructs or owns a `SchwabStreamManager` and injects a `StreamManagerRuntimeSnapshotProducer` or equivalent producer into the session. The environment-only app path deliberately returns `LIVE_RUNTIME_UNAVAILABLE` until such a producer is supplied, so CI/import/default behavior stays non-live and no repeated Schwab login can occur on Marimo refresh.
