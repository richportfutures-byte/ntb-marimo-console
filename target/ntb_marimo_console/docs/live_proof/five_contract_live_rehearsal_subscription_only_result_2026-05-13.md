# Five-Contract Schwab Live Rehearsal Subscription-Only Result - 2026-05-13

This record captures the sanitized result reported by the operator after an explicitly authorized five-contract Schwab live rehearsal attempt. This repository update did not run another live attempt, open Schwab, inspect secrets, inspect token file contents, connect, log in, or subscribe.

## Verdict

**PARTIAL / FAIL-CLOSED**

The rehearsal reached Schwab streamer credential retrieval, runtime start, live login, and live five-contract subscription.

It does **not** prove production live readiness because the bounded receive loop produced no market data. In plain terms: successful subscription is not live market-data proof.

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
| market_data_received | no |
| received_contracts_count | 0 |
| repeated_login_on_refresh | no |
| cleanup_status | ok |
| duration_seconds | 10.0 |
| values_printed | no |

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

This result improves on the prior required-environment-key blocker by proving that the explicit live path reached credential retrieval, runtime start, login, and five-contract subscription. It still proves subscription plumbing only. It does not prove:

- real LEVELONE_FUTURES delivery for ES, NQ, CL, 6E, or MGC,
- real CHART_FUTURES delivery,
- symbol entitlement or rollover correctness,
- full live-session Marimo usability,
- production live workstation readiness,
- query readiness,
- trade authorization.

Because `subscribed_contracts_count=5`, `market_data_received=no`, and `received_contracts_count=0`, the workstation must remain fail-closed from this result. No live-readiness acceptance, QUERY_READY state, D3 completion, or production release readiness can be derived from successful subscription alone.

## Production Readiness Blockers Preserved

Production release remains premature until sanitized repository evidence records:

- real LEVELONE_FUTURES market data for ES, NQ, CL, 6E, and MGC,
- real CHART_FUTURES delivery for ES, NQ, CL, 6E, and MGC,
- symbol entitlement and rollover proof,
- full live-session Marimo usability.

## Sensitive Output Review

The operator-provided output reported `values_printed=no`.

This repository record intentionally contains only boolean/status/count outcomes. It contains no credential values, token values, auth payloads, account values, customer or correl values, raw quote values, prices, or live provider URLs.

## Readiness Boundary

This subscription-only result is review evidence only. It does not alter default launch behavior, does not make live mode default, does not loosen trigger-state or query-gate provenance, and does not authorize queries or trades. Default app launch remains non-live, fixture-safe tests remain credential-free, live behavior remains explicitly opt-in, and no fixture fallback after live failure remains preserved.
