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

## Launcher

R27 adds an explicit operator entry point — `ntb_marimo_console.operator_live_launcher` — that constructs and starts an operator-owned `SchwabStreamManager` exactly once, outside the Marimo refresh path.

- Opt-in: the launcher refuses unless `NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME` (or the equivalent legacy `NTB_OPERATOR_LIVE_RUNTIME=1`) is set in the launching shell.
- Surface (names only):
  - `start_operator_live_runtime(client_factory=..., config=..., values=..., register=True, manager_builder=...) -> OperatorLiveLaunchResult`
  - `stop_operator_live_runtime(manager) -> StreamManagerSnapshot`
  - `OperatorLiveLaunchResult` (manager, producer, started_snapshot)
  - `register_operator_live_runtime_manager`, `register_operator_live_runtime_producer`, `clear_operator_live_runtime_registration`, `get_registered_operator_live_runtime_producer`
  - `OperatorLiveRuntimeOptInRequired`, `OperatorLiveRuntimeFactoryError`, `OperatorLiveRuntimeStartError`
- The operator supplies the `SchwabStreamClient` via a `client_factory` callable and a fully-populated `SchwabStreamManagerConfig` (services/symbols/fields). The launcher invokes `manager.start()` exactly once, validates the resulting snapshot is `active` with no blocking reasons, and (when `register=True`) registers the started manager so the Marimo cell's existing `build_operator_runtime_snapshot_producer_from_env()` resolves to a `StreamManagerRuntimeSnapshotProducer` wrapping it.
- Failure modes: a factory exception raises `OperatorLiveRuntimeFactoryError` with a redacted message and `__cause__` preserved; a start exception or a non-active/blocked started snapshot raises `OperatorLiveRuntimeStartError`. Neither path registers a producer or falls back to fixtures. The Marimo session continues to resolve to `LIVE_RUNTIME_UNAVAILABLE`/`LIVE_RUNTIME_ERROR`, blocking readiness and `QUERY_READY`.
- Refresh-path invariant: only `manager.snapshot()` is invoked from the Marimo refresh path. `start`, `login`, and `subscribe` are launcher-only. The 15-second `MIN_STREAM_REFRESH_FLOOR_SECONDS` continues to gate refresh frequency.
- Universe invariants: the launcher uses `final_target_contracts()` — `ES`, `NQ`, `CL`, `6E`, `MGC` — when no config is supplied. `ZN` and `GC` remain excluded; `MGC` remains Micro Gold and is not mapped to `GC`.
- The launcher imports must not read environment values, construct a Schwab client, or call `start()` at module-import time. Default pytest runs and CI continue to require no Schwab credentials.

The launcher does not select, construct, or ship a concrete `SchwabStreamClient` implementation. That is intentionally operator-supplied (or test-supplied) so this step adds the construction boundary without committing the workstation to a particular client wiring.

### Concrete client factory

R28 adds a concrete `SchwabStreamClient` wrapper at `ntb_marimo_console.schwab_stream_client`:

- `OperatorSchwabStreamClient(session)` — implements the three-method `SchwabStreamClient` Protocol by delegating to an operator-supplied `StreamerSession` collaborator. Any exception or non-success result is sanitized via `redact_sensitive_text` before reaching readiness, the renderer, or the operator-facing failure surface.
- `StreamerSession` (Protocol) — minimal abstraction with `login(config)`, `subscribe(request)`, `close()`. Operators (or a future step) supply a concrete websocket implementation.
- `StreamerSessionFactory = Callable[[SchwabStreamManagerConfig], StreamerSession]`.
- `build_operator_schwab_stream_client_factory(streamer_session_factory=...) -> ClientFactory` — returns a callable consumable by `start_operator_live_runtime(client_factory=...)`. The `streamer_session_factory` keyword is required; there is no implicit default. The builder is lazy: it does not invoke the session factory, read credentials, read tokens, fetch streamer metadata, open websockets, or perform any network work. The returned factory only invokes the session factory when the launcher itself invokes it under explicit `OPERATOR_LIVE_RUNTIME` opt-in.

R28 deliberately does not ship a concrete websocket-based `StreamerSession` implementation. Wiring `scripts/probe_schwab_levelone_futures.py` (or an equivalent in-process implementation) into a `StreamerSession` is a separate downstream step. Until that step lands, the explicit `OPERATOR_LIVE_RUNTIME` opt-in path can be exercised end-to-end with operator-supplied or test-supplied collaborators while CI/import/default behavior remains non-live and credential-free.

### Real streamer session adapter

R29 ships the production-intended in-process `StreamerSession` adapter at `ntb_marimo_console.schwab_streamer_session`:

- `OperatorSchwabStreamerSession` — concrete session that performs `ADMIN LOGIN`, `LEVELONE_FUTURES SUBS`, and `LOGOUT`/close exactly once per explicit startup. Constructed from three injected collaborators: `SchwabAccessTokenProvider`, `SchwabStreamerCredentialsProvider`, and `SchwabWebsocketFactory`.
- `dispatch_one(handler)` — receive/dispatch handoff. The session parses one inbound websocket frame, extracts each `LEVELONE_FUTURES` `data.content` entry, and forwards a normalized mapping (`provider`, `service`, `symbol`, `contract`, `message_type="quote"`, `fields`, `received_at`) to the operator-supplied handler — typically `launch.manager.ingest_message`. Returns `False` on timeout / EOF / parse failure / inactive session. The receive loop is **not** auto-spawned; it is operator-driven.
- `build_operator_schwab_streamer_session_factory(access_token_provider=..., credentials_provider=..., websocket_factory=..., fields_requested=..., timeout_seconds=...)` — validates collaborators (callable `connect`, `load_access_token`, `load_streamer_credentials`) and returns a session factory consumable by `build_operator_schwab_stream_client_factory(streamer_session_factory=...)`. Lazy: the builder does not invoke any provider; the closure only invokes them when the launcher invokes the wrapped client factory under explicit `OPERATOR_LIVE_RUNTIME` opt-in.
- `default_schwab_websocket_factory()` — returns a lazy default factory that imports `websockets.sync.client` only on first `connect()`. Module import never imports `websockets`.
- `FileAccessTokenProvider(token_path)` — lazy local-file `access_token` loader. No refresh; operators with a fresh token can rehearse, otherwise a custom provider with refresh logic is required.
- `StaticStreamerCredentialsProvider(credentials)` — operator-supplied immutable `StreamerCredentials` (the user-preference fetch remains operator/scripts-supplied; R29 does not auto-fetch user preferences from src/).
- All failure paths (provider error, malformed response, timeout, denied login, denied subscribe, ZN/GC subscription attempt, logout send failure) return `StreamClientResult(False, redacted_reason)`. The launcher converts these to `OperatorLiveRuntimeStartError` and never registers a producer; subsequent `resolve_operator_runtime_snapshot` returns `LIVE_RUNTIME_UNAVAILABLE` (no fixture fallback). All reason strings pass through `redact_sensitive_text`.

Manual rehearsal entry point::

    creds = StreamerCredentials(...)        # operator-loaded out-of-band
    captured = []

    def session_factory(config):
        session = OperatorSchwabStreamerSession(
            access_token_provider=FileAccessTokenProvider(Path(".state/schwab/token.json")),
            credentials_provider=StaticStreamerCredentialsProvider(creds),
            websocket_factory=default_schwab_websocket_factory(),
        )
        captured.append(session)
        return session

    client_factory = build_operator_schwab_stream_client_factory(streamer_session_factory=session_factory)
    launch = start_operator_live_runtime(client_factory=client_factory, config=...)

    session = captured[-1]
    while session.dispatch_one(handler=launch.manager.ingest_message):
        pass

R29 is ready for explicit manual live rehearsal **provided** the operator supplies a fresh `StreamerCredentials` (e.g., via `scripts/probe_schwab_user_preference.py`) and a fresh access token. Auto-fetch of user preferences, OAuth refresh inside src/, and a managed receive thread remain documented downstream-step candidates.

### Safe OAuth recovery

If the user-preference probe reports that the local token file has an access token but no refresh token, perform a fresh OAuth authorization-code flow locally before retrying the live probes. The OAuth prep script prints status fields only. It must not print the raw authorization URL, callback URL, authorization code, app credentials, token JSON, access token, or refresh token.

Run from `target/ntb_marimo_console/`:

```
set -a && . .state/secrets/schwab_live.env && set +a
SCHWAB_OAUTH_LIVE=true \
PYTHONPATH=src:../../source/ntb_engine/src \
python3 scripts/prepare_schwab_oauth_token.py --write-authorization-url
```

The command writes the raw authorization URL to `target/ntb_marimo_console/.state/schwab/oauth_authorization_url.txt` with owner-only permissions and prints only the relative path plus sanitized status fields. Open that local file outside chat, complete the browser authorization, then paste the redirected callback URL or raw authorization code only into the local terminal prompt. Do not paste the authorization URL, callback URL, authorization code, token JSON, or token values into chat, docs, logs, commits, or proof artifacts.

If token exchange fails after pasting a code, do not retry the same code. Schwab authorization codes are single-use and time-sensitive. Inspect only the sanitized `token_error_code`, `token_error_description_class`, `response_content_type`, and `response_decode_status` fields printed by the prep script. Use those fields to distinguish likely `invalid_grant` code reuse/expiry, redirect URI/callback mismatch, `invalid_client` app credential problems, malformed request shape, or unreadable/compressed response handling. Verify callback URL exactness locally in the shell or browser configuration without printing or pasting the callback URL. Rerun a fresh OAuth browser flow only after the diagnostics are readable and sanitized.

After the token file is written, rerun `scripts/probe_schwab_user_preference.py` under the existing explicit live gate. Rerun `scripts/run_operator_live_runtime_rehearsal.py --live` only after streamer credentials are obtained. A user-preference failure remains blocking; the operator runtime must not fall back to fixtures after a live failure.

### Manual rehearsal command

R30 ships an explicit live-gated rehearsal at `scripts/run_operator_live_runtime_rehearsal.py`. The command wires R29's `OperatorSchwabStreamerSession` through R28's stream client factory and R27's launcher, drives a bounded `dispatch_one` receive loop into the manager's `ingest_message` cache path, and prints **boolean/status keys only** — no Schwab-sensitive values appear in stdout, stderr, or the JSON payload. The script does not open `.state/secrets/schwab_live.env`; the operator sources that file in their shell first.

The expected manual command, run from `target/ntb_marimo_console/`:

```
set -a && . .state/secrets/schwab_live.env && set +a
NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME \
PYTHONPATH=src:../../source/ntb_engine/src \
python3 scripts/run_operator_live_runtime_rehearsal.py --live --duration 10
```

Required preconditions enforced by the command:

- `--live` flag (without it: `mode=blocked`, `live_flag=no`, exit 2).
- `NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME` (without it: `operator_live_runtime_env=no`, exit 2).
- `SCHWAB_APP_KEY`, `SCHWAB_APP_SECRET`, `SCHWAB_TOKEN_PATH` present (boolean only).
- `SCHWAB_TOKEN_PATH` resolves under `target/ntb_marimo_console/.state/`.
- Token file present.

Output keys (text-mode `key=value` lines or `--json` payload, sanitized):

```
mode=live|blocked
status=ok|blocked|error
repo_check=yes|no
live_flag=yes|no
operator_live_runtime_env=yes|no
env_keys_present=yes|no
token_path_under_target_state=yes|no
token_file_present=yes|no
token_fresh=yes|no|unknown
streamer_credentials_obtained=yes|no
runtime_start_attempted=yes|no
live_login_succeeded=yes|no
live_subscribe_succeeded=yes|no
subscribed_contracts_count=5
market_data_received=yes|no
received_contracts_count=N
repeated_login_on_refresh=no
cleanup_status=ok|skipped|error
duration_seconds=N
values_printed=no
```

Active front-month symbol resolution defaults to ES=`/ESM26`, NQ=`/NQM26`, CL=`/CLM26`, 6E=`/6EM26`, MGC=`/MGCM26` (calendar-dependent). Operators override at roll dates via `--symbol ROOT=KEY` (repeatable). `ZN` and `GC` are rejected at argparse and never appear in any subscription payload. The duration is clamped to `[1, 30]` seconds. The receive loop only invokes `session.dispatch_one(handler=manager.ingest_message)`; it never re-invokes login, subscribe, websocket connect, or `manager.start`. Cleanup via `stop_operator_live_runtime` runs in a `finally` block.

This step does not write into `target/ntb_marimo_console/docs/live_proof/`. Operators capture proof artifacts via the existing `scripts/capture_five_contract_live_proof.py --live` flow; that path remains unchanged.

## Safety Boundaries

- The final readiness universe remains `ES`, `NQ`, `CL`, `6E`, and `MGC`.
- Excluded final target contracts remain `ZN` and `GC`.
- `MGC` remains Micro Gold and is not mapped to `GC`.
- A missing, stale, disabled, error, unsupported, or excluded runtime snapshot blocks readiness.
- Live/runtime failure does not fall back to fixture readiness.
- Readiness remains a read-only operator visibility surface. The preserved engine remains the only decision authority, and the app still contains no broker/order/account/fill/P&L behavior.

## Remaining Live-Start Blocker

R27 adds the explicit operator-live entry point (see "Launcher" above). The remaining gap is the concrete `SchwabStreamClient` implementation that performs real network login/subscribe. Until an operator supplies one to `start_operator_live_runtime` (via `client_factory`), the environment-only app path deliberately returns `LIVE_RUNTIME_UNAVAILABLE`, so CI/import/default behavior stays non-live and no repeated Schwab login can occur on Marimo refresh.
