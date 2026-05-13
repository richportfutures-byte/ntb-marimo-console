# Five-Contract Schwab Live Rehearsal Blocked Result - 2026-05-13

This record captures the sanitized result reported by the operator after an explicitly authorized five-contract Schwab live rehearsal attempt. This repository update did not run another live attempt, open Schwab, inspect secrets, inspect token file contents, connect, log in, or subscribe.

## Verdict

**PARTIAL / FAIL-CLOSED**

The rehearsal was attempted with explicit live opt-in, but it blocked before runtime start because required Schwab live environment keys were missing.

It does **not** prove production live readiness. In plain terms: this does not prove production live readiness. It does not prove live login, live subscription, provider connection, or market-data delivery.

## Recorded Checks

| Check | Recorded value |
|---|---|
| mode | blocked |
| status | blocked |
| repo_check | yes |
| live_flag | yes |
| operator_live_runtime_env | yes |
| env_keys_present | no |
| token_path_under_target_state | no |
| token_file_present | no |
| token_file_parseable | no |
| token_contract_valid | no |
| access_token_present | no |
| refresh_token_present | no |
| token_fresh | unknown |
| streamer_credentials_obtained | no |
| runtime_start_attempted | no |
| live_login_succeeded | no |
| live_subscribe_succeeded | no |
| subscribed_contracts_count | 0 |
| market_data_received | no |
| received_contracts_count | 0 |
| repeated_login_on_refresh | no |
| cleanup_status | skipped |
| duration_seconds | 0.0 |
| values_printed | no |
| blocking_reason | required_env_keys_missing |

## Contract Scope

The intended rehearsal scope remains only the final target universe:

- ES
- NQ
- CL
- 6E
- MGC

MGC is Micro Gold. It is not GC, and GC is not a substitute for MGC.

Excluded final target contracts remain excluded:

- ZN
- GC

## Interpretation

This blocked result proves only that the explicit live gate failed closed before runtime start when required environment keys were absent. It does not prove:

- runtime start,
- provider connection,
- live login,
- live subscription,
- live market-data delivery,
- LEVELONE_FUTURES updates for ES, NQ, CL, 6E, or MGC,
- CHART_FUTURES delivery,
- symbol entitlement or rollover correctness,
- full live-session Marimo usability,
- production live workstation readiness,
- query readiness,
- trade authorization.

Because `runtime_start_attempted=no`, `live_login_succeeded=no`, `live_subscribe_succeeded=no`, `subscribed_contracts_count=0`, `market_data_received=no`, and `received_contracts_count=0`, the workstation must remain fail-closed from this result.

## Production Readiness Blockers Preserved

Production release remains blocked until sanitized repository evidence records:

- real LEVELONE_FUTURES market data for ES, NQ, CL, 6E, and MGC,
- real CHART_FUTURES delivery for ES, NQ, CL, 6E, and MGC,
- symbol entitlement and rollover proof,
- full live-session Marimo usability.

## Sensitive Output Review

The operator-provided output reported `values_printed=no`.

This repository record intentionally contains only boolean/status/count outcomes. It contains no credential values, token values, auth payloads, account values, customer or correl values, or live provider URLs.

## Readiness Boundary

This blocked result is review evidence only. It does not alter default launch behavior, does not make live mode default, does not loosen trigger-state or query-gate provenance, and does not authorize queries or trades. Default app launch remains non-live, fixture-safe tests remain credential-free, live behavior remains explicitly opt-in, and no fixture fallback after live failure remains preserved.
