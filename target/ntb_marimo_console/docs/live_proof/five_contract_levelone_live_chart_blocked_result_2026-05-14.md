# Five-Contract Schwab LEVELONE_FUTURES Live Result With CHART_FUTURES Block - 2026-05-14

This record captures the sanitized result reported by the operator after an explicitly authorized bounded live rehearsal. This repository update did not run another live attempt, open Schwab, inspect secrets, inspect token file contents, connect, log in, or subscribe.

## Verdict

**PARTIAL / FAIL-CLOSED LIVE OBSERVATION RECORDED**

The rehearsal reached live login, live five-contract subscription, and counted LEVELONE_FUTURES updates for all five final target contracts during the bounded receive window.

It does **not** prove full live workstation readiness. It does **not** prove CHART_FUTURES delivery, completed five-minute bars, query readiness, trade authorization, or execution readiness.

## Recorded Checks

| Check | Recorded value |
|---|---|
| mode | live |
| status | ok |
| live_login_succeeded | yes |
| live_subscribe_succeeded | yes |
| subscribed_contracts_count | 5 |
| market_data_received | yes |
| received_contracts_count | 5 |
| market_data_diagnostic | levelone_futures_updates_received |
| chart_data_received | no |
| chart_received_contracts_count | 0 |
| chart_completed_five_minute_contracts_count | 0 |
| chart_data_diagnostic | chart_futures_malformed_or_blocked |
| repeated_login_on_refresh | no |
| duration_seconds | 10.0 |
| values_printed | no |

## Per-Contract Recorded Status

| Contract | Display name | LEVELONE_FUTURES status | CHART_FUTURES status |
|---|---|---|---|
| ES | E-mini S&P 500 | fresh_quote_update_received | no_chart_event_received |
| NQ | E-mini Nasdaq-100 | fresh_quote_update_received | no_chart_event_received |
| CL | Crude Oil | fresh_quote_update_received | no_chart_event_received |
| 6E | Euro FX | fresh_quote_update_received | no_chart_event_received |
| MGC | Micro Gold | fresh_quote_update_received | no_chart_event_received |

MGC is Micro Gold. It is not GC, and GC is not a substitute for MGC.

Excluded final target contracts remain excluded:

- ZN
- GC

## Interpretation

This result proves bounded real LEVELONE_FUTURES delivery for ES, NQ, CL, 6E, and MGC in the exact reported run.

This result keeps CHART_FUTURES fail-closed because no chart contracts were counted and no completed five-minute bars were recorded.

The old aggregate chart diagnostic for this run was `chart_futures_malformed_or_blocked`. After this repository update, the next explicit live run will classify the chart path with narrower sanitized categories:

- `no_chart_futures_events_received`
- `chart_futures_subscribe_failed`
- `chart_futures_provider_or_entitlement_block`
- `chart_futures_unsupported_response`
- `chart_futures_malformed_or_unparseable_events`
- `chart_futures_partial_only_bars_received`
- `chart_futures_no_completed_five_minute_bars`
- `chart_futures_completed_five_minute_bars_received`

## Sensitive Output Review

The operator-provided output reported `values_printed=no`.

This repository record intentionally contains only boolean/status/count outcomes. Raw market values and raw streamer payloads were not recorded. It contains no credential values, token values, auth payloads, account values, customer or correl values, raw quote values, prices, raw streamer payloads, or live provider URLs.

## Readiness Boundary

This result is review evidence only. It does not alter default launch behavior, does not make live mode default, does not loosen trigger-state or query-gate provenance, and does not authorize queries or trades. Default app launch remains non-live, fixture-safe tests remain credential-free, live behavior remains explicitly opt-in, and no fixture fallback after live failure remains preserved.
