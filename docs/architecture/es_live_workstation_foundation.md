# ES Live Workstation Foundation

R06 adds a target-owned ES live workstation read-model foundation under `live_workstation/`.

## Scope

- The read model is ES-only.
- It consumes fixture or mocked live observable quote inputs, quote quality, completed CHART_FUTURES bar state, preserved premarket artifact levels, event lockout status, and explicit trigger definitions.
- It emits deterministic workstation states: `UNAVAILABLE`, `DORMANT`, `APPROACHING`, `TOUCHED`, `ARMED`, `QUERY_READY`, `INVALIDATED`, `BLOCKED`, `STALE`, `LOCKOUT`, and `ERROR`.
- `QUERY_READY` is a read-model state only. It does not authorize the preserved pipeline, create a real query button path, or approve execution.
- Completed five-minute confirmation requires completed one-minute support from the bar builder. Building or partial bars do not count as confirmation.
- Missing premarket artifacts, stale quote data, event lockout, missing required quote fields, symbol or contract mismatch, malformed bar state, unsupported contracts, excluded contracts, and incomplete confirmation fail closed with stable blocking reasons.
- Source classification is explicit for observed Schwab-shaped quote input, derived quote/bar facts, preserved artifacts, manual operator input, and unavailable sources.

## Non-Live Boundary

R06 does not start Schwab login, subscription, WebSocket networking, or repeated Marimo-refresh logins. Default launch remains non-live and fixture-safe.

## Authority Boundary

The ES workstation foundation is not a decision authority. The preserved engine remains the sole decision authority for bounded pipeline evaluation. R06 adds no broker, order, execution, fill, account, P&L, trade authorization, or pipeline query authorization behavior.

## Contract Boundary

R06 does not onboard `NQ`, `6E`, or `MGC` runtime/profile support. `ZN` and `GC` remain excluded from final target support, and `GC` is not a synonym for `MGC`.
