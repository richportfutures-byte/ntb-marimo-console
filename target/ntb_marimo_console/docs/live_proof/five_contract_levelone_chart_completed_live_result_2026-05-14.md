# Five-Contract Schwab LEVELONE_FUTURES And Completed CHART_FUTURES Live Result - 2026-05-14

This record captures the sanitized result reported by the operator after an explicitly authorized bounded 420-second live rehearsal. This repository update did not run another live attempt, open Schwab, inspect secrets, inspect token file contents, connect, log in, or subscribe.

## Verdict

**BOUNDED LEVELONE_FUTURES AND COMPLETED CHART_FUTURES LIVE DELIVERY RECORDED**

The rehearsal reached live login, live five-contract subscription, counted LEVELONE_FUTURES updates for all five final target contracts, and counted completed five-minute CHART_FUTURES bars for all five final target contracts during the bounded receive window.

It does **not** prove production live readiness. It does **not** prove full live-session Marimo cockpit usability, symbol entitlement and rollover correctness beyond the exact reported run, query readiness, trade authorization, or execution readiness.

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
| chart_data_received | yes |
| chart_received_contracts_count | 5 |
| chart_completed_five_minute_contracts_count | 5 |
| chart_data_diagnostic | chart_futures_completed_five_minute_bars_received |
| chart_blocking_reasons | [] |
| chart_dispatch_parse_error_count | 0 |
| chart_unsupported_response_count | 0 |
| repeated_login_on_refresh | no |
| cleanup_status | ok |
| requested_duration_seconds | 420.0 |
| effective_duration_seconds | 420.0 |
| actual_observed_duration_seconds | 420.0079059730051 |
| duration_clamped | no |
| early_exit_reason | (empty) |
| values_printed | no |

## Per-Contract Recorded Status

| Contract | Display name | LEVELONE_FUTURES status | CHART_FUTURES status | Last chart event status |
|---|---|---|---|---|
| ES | E-mini S&P 500 | fresh_quote_update_received | completed_five_minute_bar_available | completed_bar |
| NQ | E-mini Nasdaq-100 | fresh_quote_update_received | completed_five_minute_bar_available | completed_bar |
| CL | Crude Oil | fresh_quote_update_received | completed_five_minute_bar_available | completed_bar |
| 6E | Euro FX | fresh_quote_update_received | completed_five_minute_bar_available | completed_bar |
| MGC | Micro Gold | fresh_quote_update_received | completed_five_minute_bar_available | completed_bar |

MGC is Micro Gold. It is not GC, and GC is not a substitute for MGC.

Excluded final target contracts remain excluded:

- ZN
- GC

## Interpretation

This result proves, for the exact reported 420-second run:

- bounded real LEVELONE_FUTURES delivery for ES, NQ, CL, 6E, and MGC, and
- bounded real CHART_FUTURES delivery for ES, NQ, CL, 6E, and MGC through completed five-minute bars.

The CHART_FUTURES path is no longer fail-closed for lack of evidence. The prior block was a duration ceiling that prevented a run long enough to span a completed five-minute bar boundary; the duration request was honored at 420 seconds (`requested_duration_seconds=420.0`, `effective_duration_seconds=420.0`, `actual_observed_duration_seconds=420.0079059730051`, `duration_clamped=no`, `early_exit_reason` empty), and `chart_data_diagnostic=chart_futures_completed_five_minute_bars_received` with `chart_completed_five_minute_contracts_count=5` records completed-bar delivery rather than partial or building bars.

This result does not prove:

- full live-session Marimo cockpit usability,
- symbol entitlement or rollover correctness beyond the exact reported run,
- production live workstation readiness,
- query readiness,
- trade authorization,
- execution, order, fill, account, or P&L behavior.

LEVELONE_FUTURES success was not reused as CHART_FUTURES success: the two services were counted separately and both reached five distinct final target contracts. Subscription success was not treated as delivery success: completed-bar delivery was counted from received events. Building or partial bars were not treated as completed confirmation: the recorded diagnostic is the completed-bar category.

## Production Readiness Blockers Preserved

Production release remains premature until sanitized repository evidence and verification record:

- full live-session Marimo cockpit usability across the bounded live window,
- symbol entitlement and rollover proof beyond the exact reported run,
- release hardening (multi-session soak, reconnect under real loss, dedicated live-app launch wiring).

## Sensitive Output Review

The operator-provided output reported `values_printed=no`.

This repository record intentionally contains only boolean/status/count/duration outcomes. Raw market values and raw streamer payloads were not recorded. It contains no credential values, token values, auth payloads, account values, customer or correl values, raw quote values, raw bar values, prices, raw streamer payloads, or live provider URLs.

## Readiness Boundary

This result is review evidence only. It does not alter default launch behavior, does not make live mode default, does not loosen trigger-state or query-gate provenance, and does not authorize queries or trades. Default app launch remains non-live, fixture-safe tests remain credential-free, live behavior remains explicitly opt-in, and no fixture fallback after live failure remains preserved.
