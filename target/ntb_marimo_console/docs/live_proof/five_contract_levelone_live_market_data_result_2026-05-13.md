# Five-Contract Schwab LEVELONE_FUTURES Live Market Data Result - 2026-05-13

This record captures the sanitized result reported by the operator after an explicitly authorized post-fix five-contract Schwab live rehearsal. This repository update did not run another live attempt, open Schwab, inspect secrets, inspect token file contents, connect, log in, or subscribe.

## Verdict

**BOUNDED LEVELONE_FUTURES LIVE DELIVERY RECORDED**

The rehearsal reached Schwab streamer credential retrieval, runtime start, live login, live five-contract subscription, and counted LEVELONE_FUTURES market-data updates for all five final target contracts during the bounded receive window.

It does **not** prove production live readiness. It does **not** prove CHART_FUTURES delivery, full live-session Marimo usability, query readiness, trade authorization, or execution readiness.

## Recorded Checks

| Check | Recorded value |
|---|---|
| mode | live |
| status | ok |
| repo_check | yes |
| live_flag | yes |
| operator_live_runtime_env | yes |
| env_keys_present | yes |
| token_path_under_target_state | yes |
| token_file_present | yes |
| token_file_parseable | yes |
| token_contract_valid | yes |
| access_token_present | yes |
| refresh_token_present | yes |
| token_fresh | no |
| streamer_credentials_obtained | yes |
| runtime_start_attempted | yes |
| live_login_succeeded | yes |
| live_subscribe_succeeded | yes |
| subscribed_contracts_count | 5 |
| market_data_received | yes |
| received_contracts_count | 5 |
| market_data_diagnostic | levelone_futures_updates_received |
| repeated_login_on_refresh | no |
| cleanup_status | ok |
| duration_seconds | 30.0 |
| values_printed | no |

## Contract Scope

The reported market-data count was five and belongs only to the final target universe:

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

This result proves bounded live LEVELONE_FUTURES delivery for the final target universe in the exact reported run: ES, NQ, CL, 6E, and MGC.

This result does not prove:

- real CHART_FUTURES delivery,
- symbol entitlement or rollover correctness beyond the exact reported run,
- full live-session Marimo usability,
- production live workstation readiness,
- query readiness,
- trade authorization,
- execution, order, fill, account, or P&L behavior.

Because `market_data_received=yes`, `received_contracts_count=5`, and `market_data_diagnostic=levelone_futures_updates_received`, the prior subscription-only live-data gap is no longer the current LEVELONE_FUTURES proof blocker. Production readiness remains withheld because non-LEVELONE blockers remain.

## Production Readiness Blockers Preserved

Production release remains premature until sanitized repository evidence records:

- real CHART_FUTURES delivery for ES, NQ, CL, 6E, and MGC,
- symbol entitlement and rollover proof beyond the exact reported run,
- full live-session Marimo usability.

## Sensitive Output Review

The operator-provided output reported `values_printed=no`.

This repository record intentionally contains only boolean/status/count outcomes. Raw market values and raw streamer payloads were not recorded. It contains no credential values, token values, auth payloads, account values, customer or correl values, raw quote values, prices, raw streamer payloads, or live provider URLs.

## Readiness Boundary

This LEVELONE_FUTURES result is review evidence only. It does not alter default launch behavior, does not make live mode default, does not loosen trigger-state or query-gate provenance, and does not authorize queries or trades. Default app launch remains non-live, fixture-safe tests remain credential-free, live behavior remains explicitly opt-in, and no fixture fallback after live failure remains preserved.
