# CHART_FUTURES Bar Builder Foundation

R05 adds a target-owned CHART_FUTURES bar builder foundation for fixture-normalized one-minute bar ingestion and deterministic five-minute aggregation.

## Scope

- Final target contracts are `ES`, `NQ`, `CL`, `6E`, and `MGC`.
- `ZN` and `GC` are excluded from final target bar state.
- `GC` is not a synonym for `MGC`.
- One-minute bars are validated for contract, symbol, timestamps, OHLCV fields, completion state, and source shape.
- Five-minute bars are completed only when all five completed one-minute bars are present.
- Current building five-minute bars are separated from completed five-minute bars.
- Gaps, malformed records, stale data, symbol mismatch, out-of-order input, and excluded contracts create explicit blocking reasons.

## Non-Authority Boundary

The bar builder is not a decision authority. It exposes bar facts and quality state only. Partial bars are not confirmation, missing chart data fails closed, and completed-bar helpers do not produce trigger states, trade authorization, or query readiness.

## Deferred Work

R05 does not implement:

- real Schwab WebSocket networking
- trigger state engine states such as `ARMED` or `QUERY_READY`
- pipeline query gate wiring
- UI redesign
- runtime profile onboarding for `NQ`, `6E`, or `MGC`
- broker, order, execution, fill, account, or P&L behavior

Live Observable Snapshot v2 still leaves five-minute bar fields null until a later roadmap step explicitly wires completed bar read models into snapshot generation.
