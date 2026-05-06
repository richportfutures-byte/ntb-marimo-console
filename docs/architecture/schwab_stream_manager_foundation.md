# Schwab Stream Manager Foundation

R03 establishes the target-owned foundation for a future persistent Schwab stream manager. It is a design and fixture-tested lifecycle contract, not default live networking.

## Binding Defaults

- Default launch remains non-live.
- Live stream behavior is explicit opt-in only.
- CI and default tests require no Schwab credentials.
- Tests use injected fake clients only.
- Marimo refreshes must read cache snapshots only.
- Refresh/cache policy preserves the 15-second minimum floor.

## Persistent Manager Goal

The target architecture is one persistent stream manager per explicit live session. The manager logs in once, subscribes once to the configured futures services, updates a normalized local cache, and serves deterministic cache snapshots to UI code. Repeated Marimo refreshes must not create repeated Schwab logins or repeated subscriptions.

## Fail-Closed Operator States

The lifecycle contract exposes only market-data state: `disabled`, `initialized`, `connecting`, `login_pending`, `connected`, `subscribing`, `active`, `stale`, `disconnected`, `error`, `blocked`, and `shutdown`.

The stream manager may report readiness, staleness, connection loss, malformed data, symbol mismatch, missing data, and blocking reasons. It must not authorize trades or pipeline decisions.

## Boundaries

- No broker, execution, order, fill, P&L, or account behavior exists in R03.
- No default path performs real Schwab WebSocket networking.
- No fixture fallback is permitted after live failure.
- No engine decision authority changes.
- Final target contracts remain `ES`, `NQ`, `CL`, `6E`, and `MGC`.
- `ZN` remains legacy/historical and excluded from final target support.
- `GC` remains never-supported/excluded and is not a synonym for `MGC`.

## Redaction

Public events, summaries, errors, snapshots, reprs, and test-visible logs must redact secrets, tokens, auth headers, app keys, streamer endpoint details, customer identifiers, correlation identifiers, account identifiers, and authorization payload fragments.
