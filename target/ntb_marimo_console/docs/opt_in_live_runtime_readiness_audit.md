# R24 Opt-In Live Runtime Readiness Audit

## Verdict

Still premature to connect the five-contract readiness summary directly to the explicit opt-in live runtime cache.

The cache path exists and is fixture-tested through `SchwabStreamManager`, `StreamCacheSnapshot`, and `build_live_observable_snapshot_v2`. The blocker is the launch/readiness binding: the operator launch and lifecycle path do not create or retain a stream manager, and they do not pass a `StreamManagerSnapshot` or `StreamCacheSnapshot` into `build_five_contract_readiness_summary_surface`.

The summary now reports this explicitly as `NOT_WIRED` instead of implying live runtime readiness.

## Source-Backed Findings

1. Current five-contract readiness summary producer:
   `readiness_summary.py` builds `build_five_contract_readiness_summary_surface()` by iterating the final target preserved profiles and assembling each profile shell from fixture/preserved artifacts.

2. Current runtime cache path:
   `market_data/stream_manager.py` owns `SchwabStreamManager`, `StreamManagerSnapshot`, and `read_cache_snapshot()`. `market_data/stream_cache.py` owns `StreamCacheSnapshot`.

3. Current explicit opt-in live activation path:
   `SchwabStreamManagerConfig.explicit_live_opt_in` is required before login. `scripts/run_manual_live_rehearsal.py` uses the stream manager in fixture mode and explicit live/manual paths.

4. Current fixture/mock readiness path:
   Default tests and default launch use fixture/preserved artifacts and mocked clients. The current readiness summary is `non_live_fixture_safe`.

5. Current Marimo/operator launch binding:
   `operator_console_app.py` loads `load_session_lifecycle_from_env(default_mode="fixture_demo")`. `launch_config.py` attaches the readiness summary without a stream cache snapshot.

6. Current readiness source:
   The summary reads fixture/preserved app shells and disabled/default market data status. It does not read the live runtime stream cache.

7. Live failure behavior:
   The stream manager blocks on missing opt-in, login failure, subscription failure, stale heartbeat, malformed data, unsupported contracts, and excluded contracts. It does not fall back to fixture data after live failure.

8. Excluded contracts:
   `contract_universe.py` preserves final targets as `ES`, `NQ`, `CL`, `6E`, and `MGC`; excluded contracts are `ZN` and `GC`.

9. MGC identity:
   `MGC` remains Micro Gold. It is not `GC`, and the readiness/runtime surfaces must not map either symbol to the other.

10. Refresh floor:
   `MIN_STREAM_REFRESH_FLOOR_SECONDS` remains 15 seconds in the stream manager, and cache max age is floored to the same minimum.

## Exact Blocker

The explicit opt-in runtime cache is not bound into the operator launch/lifecycle state. Because no stream cache snapshot is supplied to the five-contract summary, ES, NQ, CL, 6E, and MGC live runtime readiness cannot yet be truthfully derived from that path.

Connecting it safely requires a future launch-owned, explicit-opt-in stream manager lifecycle that can provide sanitized cache snapshots without opening repeated logins per Marimo refresh, without fixture fallback after live failure, and without giving live observations decision authority.

## Preserved Boundaries

- Default launch remains non-live.
- Default tests remain fixture-safe and require no Schwab credentials.
- The readiness summary remains read-only operator visibility.
- Manual execution remains the only execution path.
- The preserved engine remains the only decision authority.
- The protected live proof artifacts and secret material are not prerequisites for this audit.
