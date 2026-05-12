# Five-Contract Schwab Live Rehearsal Result - 2026-05-12

This record captures the sanitized result reported by the operator after an explicitly authorized D3 Schwab five-contract live rehearsal attempt. This repository update did not run another live attempt, open Schwab, inspect secrets, inspect token file contents, connect, log in, or subscribe.

## Verdict

**PARTIAL / FAIL-CLOSED**

The rehearsal proves that the explicit live path reached Schwab streamer metadata retrieval, runtime start, live login, and a reported five-contract subscription without printing sensitive values.

It does **not** prove production live readiness because the bounded receive loop produced no market data. In plain terms: this does not prove production live readiness.

## Recorded Checks

| Check | Recorded value |
|---|---|
| mode | live |
| status | ok |
| duration_seconds | 15.0 |
| live_flag | yes |
| operator_live_runtime_env | yes |
| env_keys_present | yes |
| token_path_under_target_state | yes |
| token_file_present | yes |
| token_file_parseable | yes |
| access_token_present | yes |
| refresh_token_present | yes |
| token_contract_valid | yes |
| token_fresh | unknown |
| streamer_credentials_obtained | yes |
| runtime_start_attempted | yes |
| live_login_succeeded | yes |
| live_subscribe_succeeded | yes |
| subscribed_contracts_count | 5 |
| market_data_received | no |
| received_contracts_count | 0 |
| repeated_login_on_refresh | no |
| cleanup_status | ok |
| values_printed | no |
| blocking_reason | empty |

## Contract Scope

The reported subscription count was five and belongs only to the final target universe:

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

This result proves live login and subscription plumbing only. It does not prove:

- live market-data delivery,
- LEVELONE_FUTURES updates for ES, NQ, CL, 6E, or MGC,
- CHART_FUTURES delivery,
- production live workstation readiness,
- query readiness,
- trade authorization.

Because `market_data_received=no` and `received_contracts_count=0`, the workstation must remain fail-closed from this result. The next live-data readiness gap is market-data delivery proof, not login or subscription plumbing.

## Sensitive Output Review

The operator reported that no credentials, token contents, auth headers, streamer URLs, customer IDs, correl IDs, account IDs, or authorization payloads were pasted or printed in the rehearsal output.

This repository record intentionally contains only boolean/status/count outcomes. It contains no credential values, token values, auth payloads, account values, or live provider URLs.

## Readiness Boundary

This D3 record is review evidence only. It does not alter default launch behavior, does not make live mode default, does not loosen trigger-state or query-gate provenance, and does not authorize queries or trades. Default app launch remains non-live, fixture-safe tests remain credential-free, and live behavior remains explicitly opt-in.
