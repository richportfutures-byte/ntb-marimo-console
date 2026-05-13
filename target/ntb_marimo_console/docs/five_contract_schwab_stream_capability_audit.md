# Five-Contract Schwab Stream Capability Audit

Starting checkpoint: `e29387b Surface operator blocked-state reasons`

Latest reviewed checkpoint: `a57b0fa Record five-contract LEVELONE live result`

This B1 audit documents what is currently implemented versus assumed for live Schwab market data across the final target contracts `ES`, `NQ`, `CL`, `6E`, and `MGC`.

No live Schwab rehearsal was performed. No live credentials, token contents, auth headers, streamer URLs, customer IDs, correl IDs, account IDs, or authorization payloads were required or inspected. This audit does not add stream behavior, market logic, execution behavior, broker/order/account behavior, or a second decision authority.

## Classification Key

- Implemented: present in source and covered by fixture or mocked tests.
- Fixture-only: represented through fixtures, mocked clients, or manual artifact tooling, not proven against live Schwab traffic.
- Absent: not implemented in the repository.
- Unproven-live: structurally present but not validated by committed sanitized live evidence.
- Blocked-by-design: intentionally prevented by fail-closed checks or explicit-live gates.

## Current Verdict

The repository has a fail-closed, explicit-opt-in Schwab stream foundation and a tested cache/readiness path for normalized `LEVELONE_FUTURES` quote messages. A sanitized bounded five-contract `LEVELONE_FUTURES` live result is now recorded for `ES`, `NQ`, `CL`, `6E`, and `MGC`.

The repository now includes a narrow explicit-runtime `CHART_FUTURES` subscription/parsing path covered by fixture/mocked tests. Any roadmap step that assumes direct five-contract real live `CHART_FUTURES` proof is still premature until a sanitized operator-run chart artifact is recorded.

## Capability Matrix

| Area | Status | Evidence | Gap |
| --- | --- | --- | --- |
| Final target universe | Implemented | `contract_universe.py` defines `ES`, `NQ`, `CL`, `6E`, `MGC`; `ZN` and `GC` remain excluded. | None for static universe. |
| Runtime profiles | Implemented | `runtime_profiles.py` contains preserved profiles for all five final contracts. | Profiles are not live stream symbol configuration. |
| Stream manager startup | Implemented | `market_data/stream_manager.py` requires explicit live opt-in, provider, services, symbols, fields, contracts, and a client before login. | Real Schwab behavior remains unproven-live. |
| Stream cache | Implemented | `StreamCache` stores normalized records by contract and symbol, marks stale data, and redacts fields/reasons. | Cache readiness can be partial unless downstream five-contract readiness enforces all contracts. |
| `LEVELONE_FUTURES` normalized quote path | Implemented and bounded live result recorded | `schwab_streamer_session.py` builds a `LEVELONE_FUTURES` subscription and extracts quote entries; `stream_manager.py` accepts normalized quote messages into the cache; `docs/live_proof/five_contract_levelone_live_market_data_result_2026-05-13.md` records counted five-contract live receipt. | Entitlement and rollover robustness beyond the exact recorded run remain unproven. |
| One-shot futures quote adapter | Implemented, single-symbol | `adapters/schwab_futures_market_data.py` supports a bounded `LEVELONE_FUTURES` fetch path. | Default symbol is ES-oriented and does not establish five-contract streaming. |
| `CHART_FUTURES` normalized bar handling | Implemented foundation, unproven-live | `bar_builder.py` accepts normalized `CHART_FUTURES`-style mappings; `schwab_streamer_session.py` can normalize chart-style data frames; the explicit live runtime rehearsal can route chart bars into the builder. | Real Schwab `CHART_FUTURES` delivery remains unproven-live. |
| Per-contract stream symbols | Fixture-only | Manual/rehearsal tooling has static symbols `/ESM26`, `/NQM26`, `/CLM26`, `/6EM26`, `/MGCM26` and allows overrides. | No src-level dynamic symbol resolver or rollover service exists. |
| Rollover handling | Absent | Rehearsal defaults are static and operator-overridable. | A future task must define front-month resolution, rollover timing, and operator override policy. |
| Entitlement failure behavior | Implemented fail-closed foundation, unproven-live | Login, subscription, receive, malformed data, and missing data failures become blocked/error states with sanitized reasons. | Contract-specific Schwab entitlement failure shapes are not proven by live artifacts. |
| Refresh/cache discipline | Implemented | `MIN_STREAM_REFRESH_FLOOR_SECONDS = 15.0`; cache age is floored to at least 15 seconds; cache reads do not login or subscribe. | No managed live receive loop or reconnect/watchdog exists. |
| Redaction | Implemented | Stream events, client results, cache snapshots, and rehearsal reports sanitize sensitive fields and URL-like material. | Live artifacts still require operator review before commit. |
| Default launch | Blocked-by-design | `launch_config.py`, `runtime_modes.py`, and app startup default to fixture-safe, non-live behavior. | None for B1. |
| No fixture fallback after live failure | Blocked-by-design | Operator-live runtime surfaces unavailable/error states and does not substitute fixture data after live failure. | None for B1. |
| Cockpit stream capability metadata | Partial | The app attaches operator live runtime/readiness metadata, but the R14 cockpit shell is primarily fed by pipeline gate and workspace contract fields. | The cockpit does not yet receive a complete, per-contract live stream capability model that truthfully distinguishes unsupported, unavailable, stale, entitlement-blocked, and chart-unavailable live states across all five contracts. |

## Contract-by-Contract State

| Contract | Runtime profile | Static rehearsal symbol | `LEVELONE_FUTURES` stream assumption | `CHART_FUTURES` state | Live proof |
| --- | --- | --- | --- | --- | --- |
| ES | `preserved_es_phase1` | `/ESM26` | Bounded live result recorded for exact run | Fixture-only normalized bars | LEVELONE recorded; CHART pending |
| NQ | `preserved_nq_phase1` | `/NQM26` | Bounded live result recorded for exact run | Fixture-only normalized bars | LEVELONE recorded; CHART pending |
| CL | `preserved_cl_phase1` | `/CLM26` | Bounded live result recorded for exact run | Fixture-only normalized bars | LEVELONE recorded; CHART pending |
| 6E | `preserved_6e_phase1` | `/6EM26` | Bounded live result recorded for exact run | Fixture-only normalized bars | LEVELONE recorded; CHART pending |
| MGC | `preserved_mgc_phase1` | `/MGCM26` | Bounded live result recorded for exact run | Fixture-only normalized bars | LEVELONE recorded; CHART pending |

`MGC` is treated as its own final target contract. It is not `GC`, is not mapped to `GC`, and does not re-enable `GC`.

## Stream Manager And Cache Details

`SchwabStreamManagerConfig` defaults to disabled provider mode. Live startup requires explicit opt-in plus populated service, symbol, field, contract, and client configuration. Unsupported, excluded, never-supported, missing, login-failed, subscription-failed, malformed, stale, and heartbeat-failed states block readiness.

`SchwabStreamManager.start()` performs at most one login and one subscription for a start attempt. Repeated cache reads use `read_cache_snapshot()` and do not relogin or resubscribe. `check_heartbeat()` and cache max-age handling preserve the 15-second minimum floor.

`StreamCacheSnapshot.ready` is intentionally cache-local. It means the cache is active, nonempty, and not stale/error-blocked. Five-contract completeness is enforced downstream by live observable/readiness builders that require final target contract coverage and required quote/session fields.

## LEVELONE_FUTURES State

The production streamer session builds `ADMIN LOGIN`, `LEVELONE_FUTURES SUBS`, and logout/close messages. It extracts `LEVELONE_FUTURES` data entries into normalized quote records with service, symbol, inferred contract, message type, fields, and received timestamp.

The one-shot Schwab futures market-data adapter also normalizes `LEVELONE_FUTURES` field ids into quote snapshots. That adapter remains single-symbol and does not prove persistent five-contract streaming.

Live `LEVELONE_FUTURES` behavior for all five final contracts is implemented as a foundation and has bounded proof for the exact recorded run. That proof does not establish `CHART_FUTURES`, full live-session Marimo usability, or entitlement and rollover robustness beyond the exact run.

## CHART_FUTURES State

`ChartFuturesBarBuilder` defines a normalized bar acceptance and aggregation path for `CHART_FUTURES`-style records. It rejects unsupported services, excluded contracts, missing OHLCV fields, symbol mismatches, out-of-order bars, and gap states. It distinguishes completed one-minute bars from building bars and aggregates usable five-minute bars.

The production-intended Schwab streamer session can subscribe to `CHART_FUTURES`, normalize chart-style data frames into bar messages, and let the explicit runtime receive loop pump those messages into `ChartFuturesBarBuilder`. This path is fixture/mocked-tested only at this checkpoint; real Schwab `CHART_FUTURES` delivery remains unproven-live.

## Symbol And Rollover State

The source tree preserves final target contract roots, not an authoritative live symbol calendar. Rehearsal tooling includes static active-symbol defaults for `ES`, `NQ`, `CL`, `6E`, and `MGC`, with explicit operator overrides. `ZN` and `GC` overrides are rejected.

There is no dynamic rollover implementation, no exchange-calendar front-month resolver, and no automated symbol update in default app startup. Rollover support is absent and should not be assumed from the static rehearsal defaults.

## Entitlement And Failure State

The repository has fail-closed handling for login failure, subscription failure, missing stream client, unsupported/excluded contracts, stale heartbeat, stale cache records, malformed messages, missing fields, and missing runtime snapshots. These states are surfaced as blocked, disabled, stale, unavailable, or error readiness states with sanitized text.

What is not proven is the exact shape of Schwab entitlement failures for each final contract. Until sanitized live evidence exists, entitlement behavior is implemented only as a generic fail-closed foundation and remains unproven-live per contract.

## Refresh And Default Launch State

Default launch remains non-live and fixture-safe. Environment-only startup does not create a Schwab session or open repeated Schwab logins per Marimo refresh. Operator live runtime construction is explicit and separate from default launch.

The stream manager and runtime snapshot producer preserve the refresh boundary: snapshot/cache reads do not call `start()`, login, subscribe, OAuth, broker APIs, account APIs, fill APIs, or execution APIs.

## Redaction State

Stream events, client results, cache fields, cache blocking reasons, and manual/live rehearsal reports route text through redaction helpers before operator-facing output. Tests cover token-like strings, authorization material, customer/correl/account identifiers, URL-like values, and secret-path leakage.

This redaction layer is implemented, but real live proof artifacts still require operator review before commit because no automated sanitizer can prove every future vendor payload shape.

## Cockpit Metadata Gap

The app can attach operator-live runtime metadata and five-contract readiness summary surfaces. The R14 cockpit shell can render operator-readable blocked states from its existing contract.

However, the cockpit does not yet receive a complete per-contract live stream capability contract that distinguishes, for each final target, live stream service availability, symbol resolution, entitlement outcome, live quote freshness, live chart availability, and rollover confidence. The current cockpit should not claim more than the upstream contract supplies.

## Future Tasks

1. Define the `CHART_FUTURES` delivery contract before treating chart bars as live-available.
2. Add a src-level symbol resolution contract for ES, NQ, CL, 6E, and MGC, including rollover policy and operator overrides.
3. Extend the stream session to subscribe to and parse live `CHART_FUTURES`, if Schwab entitlement and payload shape are verified.
4. Add contract-specific entitlement failure classification after observing sanitized Schwab failure shapes.
5. Add a managed receive loop, reconnect/backoff, and watchdog without allowing Marimo refresh to create repeated logins.
6. Pass truthful per-contract stream capability metadata into the cockpit without allowing display objects to enable query readiness.
7. Record a sanitized operator-run five-contract `CHART_FUTURES` live proof artifact before any roadmap step claims live chart delivery.

## B1 Boundary

This audit did not change runtime behavior. It did not run live harnesses, inspect secret state, modify `source/ntb_engine`, loosen query-gate provenance, or change default launch. No regression test was added because the current fail-closed invariants already have targeted fixture/mocked coverage and this prompt found no dangerous runtime false assumption requiring a code fix.
