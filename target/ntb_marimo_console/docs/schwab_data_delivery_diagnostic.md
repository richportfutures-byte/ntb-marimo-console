# Schwab Data Delivery Diagnostic

Date: 2026-05-12

Starting checkpoint: `03717fc Cut NTB Marimo Console release candidate`

Scope: diagnose why the D3 five-contract live Schwab rehearsal reported `live_login_succeeded=yes`, `live_subscribe_succeeded=yes`, `market_data_received=no`, and `received_contracts_count=0`.

No live rehearsal was run for this diagnostic. No Schwab secret env file, live credential, token content, authorization header, streamer URL, customer id, correl id, account id, or authorization payload was inspected or printed.

## Bottom Line

The D3 zero-data result cannot be attributed to market hours alone from the committed sanitized evidence. The artifact proves login and subscription plumbing only; it does not include the run timestamp, exchange session state, Schwab raw frame sequence, or any sanitized evidence showing whether data frames arrived and were rejected, delayed, or never sent.

Two code-level receive-path risks were confirmed and fixed:

1. `subscribe()` drained non-ack frames while waiting for the `LEVELONE_FUTURES` SUBS ack and could drop valid data frames received before the ack.
2. The rehearsal receive pump stopped after the first `dispatch_one()` false result, so one quiet receive interval could end the bounded observation window early.

After these fixes, a future explicit live rehearsal can more cleanly distinguish true Schwab/vendor/exchange non-delivery from local receive-loop loss.

## Market-Hours Context

CME-listed futures in the final target universe are not limited to U.S. cash-market regular trading hours. CME's public contract pages describe E-mini S&P 500 and E-mini Nasdaq-100 Globex trading as Sunday through Friday, 6:00 p.m. to 5:00 p.m. ET, with a short daily pause; WTI crude oil is likewise described as nearly 24-hour access or Sunday through Friday 6:00 p.m. to 5:00 p.m. ET; Micro Gold is listed as Sunday through Friday 5:00 p.m. to 4:00 p.m. CT with a daily one-hour break.

Sources reviewed:

- CME E-mini S&P 500 contract page: https://www.cmegroup.com/markets/equities/sp/e-mini-sandp500.contractSpecs.html and localized contract-spec text showing Globex Sunday-Friday 6:00 p.m.-5:00 p.m. ET.
- CME E-mini Nasdaq-100 contract page/search result text: https://www.cmegroup.com/markets/equities/nasdaq/e-mini-nasdaq-100.contractSpecs.html and localized contract-spec text showing Globex Sunday-Friday 6:00 p.m.-5:00 p.m. ET.
- CME WTI crude oil contract page: https://www.cmegroup.com/markets/energy/crude-oil/light-sweet-crude.contractSpecs.html
- CME Micro Gold fact card: https://www.cmegroup.com/market-regulation/files/gold-futures-and-options-fact-card.pdf

This makes "outside cash/RTH" an incomplete explanation. A run during an exchange maintenance break, weekend closure, holiday halt, expired/inactive month, or broker-side no-update state could still explain no quote frames, but the committed D3 record does not prove any of those timing conditions.

## Candidate Verdicts

| Candidate | Verdict | Finding |
|---|---|---|
| A. Market hours | UNKNOWN | No D3 timestamp or session-state evidence is committed. Outside regular cash-market hours alone is not enough because the requested futures trade on extended Globex sessions. A closed maintenance/holiday/weekend window remains possible but unproven. |
| B. Subscribe ack drain | CONFIRMED | `OperatorSchwabStreamerSession.subscribe()` consumed frames until the SUBS ack. Before this fix, valid data frames that arrived before the ack were not handed to the manager. Fixed by buffering parseable pre-ack data frames for `dispatch_one()`. |
| C. Receive timeout | CONFIRMED | The rehearsal pump exited the bounded receive loop on the first `dispatch_one()` false result. Because `dispatch_one()` returns false for timeout as well as inactive/EOF, one quiet interval could prematurely record zero delivery. Fixed by continuing until the requested bounded duration expires. |
| D. Symbol format | UNLIKELY | The subscription payload builds `keys` as a comma-joined string from configured symbols. The default five-contract plan is `/ESM26,/NQM26,/CLM26,/6EM26,/MGCM26`, preserving MGC as Micro Gold and not using GC. |
| E. Field ID format | UNLIKELY | The subscription payload formats fields with `",".join(str(field_id)...)`, producing `0,1,2,3,4,5` for the default request. |
| F. Contract extraction | UNLIKELY | `_contract_from_symbol()` matches the expected Schwab-style futures keys for the final target symbols, including `/6EM26` and `/MGCM26`. It would not match an undocumented alternate vendor key shape, but no raw data frame evidence shows that occurred in D3. |
| G. Stream manager symbol validation | UNLIKELY | `SchwabStreamManagerConfig.__post_init__()` uppercases configured symbols, and `extract_data_entries()` uppercases Schwab keys before manager ingestion. If Schwab echoes the requested keys, manager validation accepts them. Alternate vendor key shapes remain unproven rather than confirmed. |

## Code Changes Made

### Pre-ack data buffering

File: `src/ntb_marimo_console/schwab_streamer_session.py`

`OperatorSchwabStreamerSession` now keeps an internal pending data-frame queue. While `subscribe()` waits for the `LEVELONE_FUTURES` SUBS ack, non-ack frames are parsed for data entries. Valid entries are buffered and delivered by the next `dispatch_one()` call before another websocket receive is attempted.

This preserves explicit-live behavior and does not add any default startup, credential, account, broker, order, fill, P&L, or execution path.

### Receive-loop duration handling

File: `scripts/run_operator_live_runtime_rehearsal.py`

`_pump_receive_loop()` now keeps observing until the bounded duration expires after a quiet `dispatch_one()` result. This avoids turning one receive timeout into a definitive zero-data observation for the whole rehearsal window.

The script remains manual-only and explicit-live only. The default duration bounds are unchanged, default launch remains non-live, and the 15-second stream refresh floor remains unchanged.

## Tests Added

- `tests/test_schwab_streamer_session.py::OperatorSchwabStreamerSessionSubscribeTests::test_subscribe_preserves_data_frame_received_before_ack_for_dispatch`
- `tests/test_run_operator_live_runtime_rehearsal.py::RehearsalCliBlockingTests::test_receive_pump_continues_after_initial_quiet_dispatch_until_duration`

Both tests use fakes/mocks and require no Schwab credentials.

## Residual Unknowns

The following still require a future operator-authorized live artifact to resolve:

- Whether Schwab sends `LEVELONE_FUTURES` data for all five final target contracts during the selected session.
- Whether the selected contract months were active and entitled at the time of the rehearsal.
- Whether Schwab returns any alternate symbol key shape in live data frames.
- Whether the D3 run occurred during a maintenance break, weekend/holiday halt, or other closed session.

Until a future sanitized live artifact records actual market-data delivery, the correct readiness classification remains partial/fail-closed: login and subscription plumbing proven; market-data delivery not proven.
