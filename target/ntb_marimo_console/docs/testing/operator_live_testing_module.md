# Operator Live Testing Module

## Prerequisites

- Valid Schwab OAuth token at the configured token path under `.state/secrets/`
- `.state/secrets/schwab_live.env` present with required env vars
- Working directory: `target/ntb_marimo_console`

## Credential-free gate (run first)

```bash
PYTHONPATH="src:../../source/ntb_engine/src:." uv run python scripts/run_operator_live_runtime_rehearsal.py --readiness-gate
```

Must show `rehearsal_ready_to_run=yes` before any live command.

## Live rehearsal (60 seconds)

```bash
set +x
set -a
. .state/secrets/schwab_live.env >/dev/null 2>&1
set +a
NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME \
  PYTHONPATH="src:../../source/ntb_engine/src:." \
  uv run python scripts/run_operator_live_runtime_rehearsal.py --live --duration 60
```

## What to confirm

| Label | Expected |
|---|---|
| live_login_succeeded | yes |
| live_subscribe_succeeded | yes |
| subscribed_contracts_count | 5 |
| received_contracts_count | 5 |
| repeated_login_on_refresh | no |
| values_printed | no |

Per contract (ES, NQ, CL, 6E, MGC):

| Label | Expected |
|---|---|
| provider | connected |
| readiness | LIVE_RUNTIME_CONNECTED |
| quote | quote available |
| missing_fields | none |
| query_ready | no |

## What must remain blocked

- `query_ready=no` for all contracts unless the preserved engine pipeline gate produces QUERY_READY provenance
- Chart completed five-minute bars require at least 5 minutes of live data; use `--duration 420` for chart proof

## Chart proof (7 minutes)

Same command with `--duration 420`. Confirm `chart_completed_five_minute_contracts_count=5`.

## Fixture default launch (non-live)

```bash
python3 scripts/launch_operator_cockpit.py --dry-run
```

Must show `mode=fixture_demo`, `operator_runtime=SAFE_NON_LIVE`.

## Do not paste

- Token contents, auth headers, app keys, secrets
- Raw quote values, raw bar values, raw streamer payloads
- Streamer URLs, customer IDs, account IDs, authorization payloads
- The contents of `.state/secrets/schwab_live.env`

## Contracts

ES, NQ, CL, 6E, MGC only. ZN and GC are excluded. MGC is Micro Gold (not GC).
