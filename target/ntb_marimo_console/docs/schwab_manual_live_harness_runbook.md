# Schwab Manual Live Harness Runbook

## Purpose

This runbook documents the manual opt-in live verification path for Schwab futures market data.
The harness proves that live quote data can reach the existing display-only market-data projection.
It is not normal app startup wiring.

## Current stopping point

Schwab live market data remains manual-harness-only.
Normal startup remains disabled/null by default.
Pytest remains mocked and non-live.
`runtime_profiles.py` and `launch_config.py` are not live activation points.
UI, state, and workflow behavior remain unchanged.

## Manual command

Run from the repository root:

```bash
env PYTHONDONTWRITEBYTECODE=1 python3 target/ntb_marimo_console/scripts/run_schwab_market_data_live_harness.py --live --symbol /ESM26 --fields 0,1,2,3,4,5 --timeout-seconds 10 --token-path target/ntb_marimo_console/.state/schwab/token.json
```

## Expected sanitized success shape

```text
SCHWAB_MARKET_DATA_LIVE_HARNESS_PASS
provider=schwab
symbol=<symbol>
status=Schwab quote
bid=<value or N/A>
ask=<value or N/A>
last=<value or N/A>
quote_time=<timestamp or unknown>
market_data_received=yes
```

## Safety invariants

- Requires explicit `--live`.
- No live calls in pytest.
- No implicit Schwab construction during normal startup.
- No probe import path in app code.
- No order placement.
- No quote-driven workflow decisions.
- No raw token, secret, customer ID, correl ID, account number, full URL, auth header, or payload output.
- Token path must remain under `target/ntb_marimo_console/.state/`.

## Failure interpretation

An interpreter missing error is environment setup, not a Schwab failure.
`market_data_received=no` means live data was not proven.
Failures should be reported by sanitized failure category only.
Do not paste secrets, raw payloads, auth headers, account numbers, customer IDs, correl IDs, or full streamer URLs into issue reports.

## Non-goals

- App live startup activation.
- Runtime profile integration.
- Launch config live wiring.
- UI, state, or workflow integration.
- Order routing.
- Replacement for the existing diagnostic probe.

## Future work, deferred

- Dedicated live app launch mode.
- Multi-symbol support.
- Better operator UX.
- Extended soak/reconnect testing.
- Production monitoring.
- Workflow, risk, or recommendation integration.
