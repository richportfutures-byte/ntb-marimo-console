# Live Observable Snapshot v2

R04 adds a target-owned live observable snapshot contract that reads normalized stream-cache state and emits deterministic, JSON-serializable market-state data for `ES`, `NQ`, `CL`, `6E`, and `MGC`.

## Scope

- The primary contract map contains only final target contracts: `ES`, `NQ`, `CL`, `6E`, and `MGC`.
- `ZN` and `GC` are excluded from the primary contract map.
- `MGC` is labeled as Micro Gold where a label is needed; `GC` is not a synonym.
- The snapshot reads cache state only. It does not start Schwab login, subscription, or networking.
- Default launch remains non-live.

## Quality Doctrine

Snapshot v2 is not a decision authority. Live data may arm, block, or annotate later gates, but it does not approve trades, authorize pipeline queries, or create execution behavior.

Missing required quote fields, stale timestamps, provider error/disconnection, and symbol mismatch fail closed through explicit blocking reasons. Missing DXY, yield, ES-relative strength, session-sequence, and event-lockout context remains unavailable rather than inferred.

## Deferred Work

R04 does not implement:

- `CHART_FUTURES` bar aggregation
- 5-minute bar quality gates
- trigger state engine states such as `ARMED` or `QUERY_READY`
- pipeline query gate wiring
- runtime profile onboarding for `NQ`, `6E`, or `MGC`
- broker, order, execution, fill, account, or P&L behavior
