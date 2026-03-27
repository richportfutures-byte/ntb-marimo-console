# NinjaTradeBuilder Operator Quickstart

## Purpose

This is the smallest supported local run path for the current branch.

It is intended for operator verification and smoke execution, not production automation.

## Prerequisites

- Python `3.11+`
- run from the repo root
- `GEMINI_API_KEY` set in the shell environment

Optional provider policy env vars:

- `NINJATRADEBUILDER_GEMINI_MODEL`
  Default: `gemini-3.1-pro-preview`
- `NINJATRADEBUILDER_GEMINI_TIMEOUT_SECONDS`
  Default: `20`
  Minimum: `10`
- `NINJATRADEBUILDER_GEMINI_MAX_RETRIES`
  Default: `1`
- `NINJATRADEBUILDER_GEMINI_RETRY_INITIAL_DELAY_SECONDS`
  Default: `1.0`
- `NINJATRADEBUILDER_GEMINI_RETRY_MAX_DELAY_SECONDS`
  Default: `4.0`

Install with:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
```

If you want the Databento-backed historical source path, install the optional extra:

```bash
.venv/bin/python -m pip install -e '.[dev,databento]'
```

## Canonical model

Use `gemini-3.1-pro-preview` for the current validated branch baseline.

## Operator path overview

Treat the workflow as two separate phases:

1. upstream packet compilation
2. runtime execution against the frozen packet

The current compiler surface supports:

- `ES` with hardened fixture-backed compilation and optional Databento-backed historical sourcing
- `CL` with a deterministic fixture-backed compiler v1 path
- `6E` with a deterministic fixture-backed compiler v1 path
- `MGC` with a deterministic fixture-backed compiler v1 path and optional Databento-backed historical sourcing
- `NQ` with a deterministic fixture-backed compiler v1 path and optional Databento-backed historical sourcing
- `ZN` with a deterministic fixture-backed compiler v1 path

Both paths still depend on one minimal manual overlay for the two fields that are intentionally not
auto-derived from upstream inputs.

## Readiness verification harness

The readiness verification harness is the operator-facing path for running live Gemini verification against the frozen `readiness_engine_output_v1` contract.

Use it for:

- operator-triggered live verification of readiness prompt behavior
- producing bounded JSON artifacts for audit review
- concise pass/fail diagnosis by contract

Do **not** use it for:

- CI live Gemini execution
- autonomous polling, monitoring, or scheduling
- altering the readiness schema or fail-closed doctrine

### Readiness verification environment

Required environment variable:

- `GEMINI_API_KEY`

Optional provider policy env vars are the same ones used by the main runtime CLI:

- `NINJATRADEBUILDER_GEMINI_MODEL`
- `NINJATRADEBUILDER_GEMINI_TIMEOUT_SECONDS`
- `NINJATRADEBUILDER_GEMINI_MAX_RETRIES`
- `NINJATRADEBUILDER_GEMINI_RETRY_INITIAL_DELAY_SECONDS`
- `NINJATRADEBUILDER_GEMINI_RETRY_MAX_DELAY_SECONDS`

### Readiness verification command surface

Inspect the operator help surface with:

```bash
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.readiness_verify --help
```

The CLI supports three explicit input modes:

1. `--fixture` for deterministic fixture-backed verification
2. `--packet-file` for packet JSON that must be converted into readiness runtime inputs
3. `--runtime-input-file` for prebuilt readiness runtime input JSON

Target selection is also explicit:

- `--contract <symbol>` for one contract
- `--all-contracts` for a packet-bundle sweep across exactly `ES`, `NQ`, `CL`, `ZN`, `6E`, and `MGC`

Exit semantics are operator-script friendly:

- exit `0`: every requested verification passed
- exit `1`: the run executed but one or more contract verifications failed
- exit `2`: operator input or configuration was invalid before a usable verification run could proceed

### Readiness verification examples

Single-contract deterministic fixture verification:

```bash
export GEMINI_API_KEY=your_existing_key
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.readiness_verify \
  --fixture \
  --contract ZN
```

Single-contract explicit packet-file verification:

```bash
export GEMINI_API_KEY=your_existing_key
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.readiness_verify \
  --packet-file ./build/es.packet.json \
  --trigger-file tests/fixtures/readiness/zn_recheck_trigger.valid.json \
  --contract ES
```

Single-contract explicit runtime-input verification:

```bash
export GEMINI_API_KEY=your_existing_key
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.readiness_verify \
  --runtime-input-file tests/fixtures/readiness/zn_runtime_inputs.valid.json \
  --trigger-file tests/fixtures/readiness/zn_recheck_trigger.valid.json \
  --contract ZN
```

All-contract packet-bundle sweep:

```bash
export GEMINI_API_KEY=your_existing_key
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.readiness_verify \
  --packet-file tests/fixtures/packets.valid.json \
  --trigger-file tests/fixtures/readiness/zn_recheck_trigger.valid.json \
  --all-contracts
```

### Readiness verification artifacts

Artifacts are written to `./artifacts/readiness-verification/<timestamp>.json` by default, or to the path supplied via `--artifact-file`.

Each artifact contains:

- top-level run metadata
- per-contract verification results
- the Gemini model identifier
- invocation mode and source file references
- a SHA-256 digest of the rendered prompt
- validation status
- explicit failure classification
- a concise operator summary string per contract

Example artifact shape:

```json
{
  "artifact_schema": "readiness_verification_run_v1",
  "run": {
    "invocation_mode": "single_contract",
    "model": "gemini-3.1-pro-preview",
    "success": true,
    "summary": "Readiness verification passed for 1/1 contract(s)."
  },
  "results": [
    {
      "contract": "ZN",
      "passed": true,
      "summary": "ZN: PASS (validated).",
      "failure_classification": null,
      "prompt": {
        "prompt_id": 10,
        "rendered_prompt_sha256": "<sha256>"
      },
      "validation": {
        "outcome": "validated",
        "output_boundary": "readiness_engine_output"
      }
    }
  ]
}
```

Interpretation guidance:

- `run.success = true` means every requested contract passed validation
- `results[].failure_classification` shows the first operator-relevant failure bucket
- `results[].validated_output` contains the validated readiness payload when a contract passes
- `results[].debug.raw_model_output_excerpt` is intentionally bounded for debugging and is not a full provider transcript

Live Gemini readiness verification remains operator-invoked only and is not part of CI.

## Phase 1: compile one ES historical packet

The compiler builds one frozen `historical_packet_v1` JSON file plus a provenance sidecar.

### Fixture-backed historical path

Copy-paste-safe compile command:

```bash
mkdir -p ./build
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.packet_compiler.cli \
  --contract ES \
  --historical-input tests/fixtures/compiler/es_historical_input.valid.json \
  --overlay tests/fixtures/compiler/es_overlay.assisted.valid.json \
  --calendar-input tests/fixtures/compiler/es_calendar.valid.json \
  --breadth-input tests/fixtures/compiler/es_breadth.valid.json \
  --index-cash-tone-input tests/fixtures/compiler/es_index_cash_tone.valid.json \
  --cumulative-delta-input tests/fixtures/compiler/es_cumulative_delta.valid.json \
  --output ./build/es.packet.json
```

This writes:

- `./build/es.packet.json`
- `./build/es.packet.provenance.json`

The compiler currently derives and records provenance for:

- prior RTH high / low / close
- overnight high / low
- current session VAH / VAL / POC
- previous session VAH / VAL / POC
- 20-day average session range
- current session volume vs average
- VWAP
- session range
- initial balance high / low / range
- weekly open
- a conservative overlay-assist subset that is not part of the minimal manual payload:
  - `attached_visuals` defaults to all false when omitted
  - `major_higher_timeframe_levels`, `key_hvns`, `key_lvns`,
    `singles_excess_poor_high_low_notes`, and `cross_market_context` default to `null`
  - `data_quality_flags` defaults to `[]`

`initial balance` and `weekly open` are recorded in the provenance sidecar because the frozen
runtime packet schema does not have dedicated top-level fields for them.

### Databento-backed historical path

The fixture-backed path above remains the deterministic default for tests, CI, and offline operator
verification.

To source only the ES historical input from Databento instead, provide:

- `DATABENTO_API_KEY` in the shell environment
- a Databento request JSON such as
  `tests/fixtures/compiler/es_databento_request.valid.json`

Copy-paste-safe Databento compile command:

```bash
export DATABENTO_API_KEY=your_existing_key
mkdir -p ./build
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.packet_compiler.cli \
  --contract ES \
  --historical-source databento \
  --databento-request tests/fixtures/compiler/es_databento_request.valid.json \
  --overlay tests/fixtures/compiler/es_overlay.assisted.valid.json \
  --calendar-input tests/fixtures/compiler/es_calendar.valid.json \
  --breadth-input tests/fixtures/compiler/es_breadth.valid.json \
  --index-cash-tone-input tests/fixtures/compiler/es_index_cash_tone.valid.json \
  --cumulative-delta-input tests/fixtures/compiler/es_cumulative_delta.valid.json \
  --output ./build/es.packet.json
```

To source `cumulative_delta` from Databento as well, keep the same command and replace only the
cumulative-delta input path:

```bash
export DATABENTO_API_KEY=your_existing_key
mkdir -p ./build
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.packet_compiler.cli \
  --contract ES \
  --historical-source databento \
  --databento-request tests/fixtures/compiler/es_databento_request.valid.json \
  --overlay tests/fixtures/compiler/es_overlay.assisted.valid.json \
  --calendar-input tests/fixtures/compiler/es_calendar.valid.json \
  --breadth-input tests/fixtures/compiler/es_breadth.valid.json \
  --index-cash-tone-input tests/fixtures/compiler/es_index_cash_tone.valid.json \
  --cumulative-delta-source databento \
  --databento-cumulative-delta-request tests/fixtures/compiler/es_databento_cumulative_delta_request.valid.json \
  --output ./build/es.packet.json
```

Databento request contract:

- `contract`
- `dataset`
- `symbol`
- `stype_in`
- `current_session_date`
- `bar_schema`
- `trades_schema`

Databento cumulative-delta request contract:

- `contract`
- `dataset`
- `symbol`
- `stype_in`
- `current_session_date`
- `trades_schema`

Compiler-side integrity checks are strict and fail closed:

- `prior_rth_bars`, `overnight_bars`, and `current_rth_bars` must be non-empty, strictly
  timestamp-ascending, and free of duplicate timestamps
- `current_rth_bars` must all fall on one session date
- `prior_rth_bars` must represent a prior date relative to the current session
- `overnight_bars` must fall strictly between prior RTH and current RTH with no overlap
- `weekly_open_bar` must not be later than the first current RTH bar
- initial balance is derived from all `current_rth_bars` with
  `first_timestamp <= timestamp < first_timestamp + 60 minutes`, and the compiler requires at
  least two bars spanning at least 30 minutes inside that window
- `prior_rth_volume_profile` and `current_rth_volume_profile` are now required historical inputs
  for deterministic profile derivation
- each profile must contain at least three price levels on a strict `0.25` ES tick ladder with
  ascending unique prices and positive volume
- `prior_20_rth_sessions` is now required historical input for deterministic `avg_20d_session_range`
- `prior_20_rth_sessions` must contain exactly 20 completed prior RTH sessions with unique
  ascending dates, and the final entry must match the prior session high/low from `prior_rth_bars`
- `prior_20_rth_observed_volumes` is now required historical input for deterministic
  `current_volume_vs_average`
- `prior_20_rth_observed_volumes` must contain exactly 20 positive observed-volume entries on the
  same ascending session dates as `prior_20_rth_sessions`
- `event_calendar_remainder` is now sourced from a dedicated ES calendar input file rather than the
  manual overlay payload
- the dedicated calendar source must validate as schema-correct `EventCalendarEntry` objects, so
  released events require `minutes_since`, upcoming events require `minutes_until`, and malformed
  calendar rows fail closed before packet compilation
- `breadth` is now sourced from a dedicated ES breadth input file rather than the manual overlay
  payload
- the dedicated breadth source must provide a non-empty `breadth` string and malformed or missing
  breadth input fails closed before packet compilation
- `index_cash_tone` is now sourced from a dedicated ES index-cash-tone input file rather than the
  manual overlay payload
- the dedicated index-cash-tone source must validate to one of the existing schema literals, and
  malformed or missing input fails closed before packet compilation
- `cumulative_delta` is now sourced from a dedicated ES cumulative-delta input file rather than the
  manual overlay payload
- the dedicated cumulative-delta source must provide a finite numeric `cumulative_delta`, and
  malformed or missing input fails closed before packet compilation
- the Databento-backed historical source requires `DATABENTO_API_KEY`, only supports
  `bar_schema=ohlcv-1m` and `trades_schema=trades`, and fails closed on malformed provider
  responses, incomplete 20-session coverage, or ambiguous symbol coverage
- the Databento-backed cumulative-delta source also requires `DATABENTO_API_KEY`, only supports
  `trades_schema=trades`, maps bid-side trades to positive signed volume and ask-side trades to
  negative signed volume, and fails closed on malformed side/size fields, missing current-session
  trade coverage, or ambiguous symbol coverage

Still-manual ES overlay fields are:

- `challenge_state`
- `opening_type`

The minimal operator overlay JSON now contains only:

- `contract`
- `challenge_state`
- `opening_type`

`challenge_state` remains manual because it is operator/challenge-state input, not market-data
derivation.

`opening_type` remains manual because the current upstream ES compiler inputs are sufficient for
objective profile, range, and matched-window volume calculations, but they do not provide a clean
non-heuristic way to classify `Open-Drive`, `Open-Test-Drive`, `Open-Rejection-Reverse`, or
`Open-Auction` without embedding interpretive market-structure logic into the compiler.

`event_calendar_remainder` is no longer embedded in the ES overlay JSON. Supply it through a
dedicated upstream calendar source such as `tests/fixtures/compiler/es_calendar.valid.json`.

`breadth` is no longer embedded in the ES overlay JSON. Supply it through a dedicated upstream
breadth source such as `tests/fixtures/compiler/es_breadth.valid.json`.

`index_cash_tone` is no longer embedded in the ES overlay JSON. Supply it through a dedicated
upstream source such as `tests/fixtures/compiler/es_index_cash_tone.valid.json`.

`cumulative_delta` is no longer embedded in the ES overlay JSON. Supply it through a dedicated
upstream source such as `tests/fixtures/compiler/es_cumulative_delta.valid.json`, or through
Databento with `--cumulative-delta-source databento` and
`tests/fixtures/compiler/es_databento_cumulative_delta_request.valid.json`.

### CL boundary summary

Current CL boundary split:

- provider-backed:
  - CL historical market input via Databento
  - CL `eia_timing` via EIA
- upstream-derived from CL historical input:
  - `realized_volatility_context`
- fixture-backed:
  - `oil_specific_headlines`
  - `liquidity_sweep_summary`
  - `dom_liquidity_summary`
- manual:
  - `challenge_state`
  - `opening_type`

The fixture-backed CL compile path remains the deterministic default for tests, CI, and offline
operator verification. It compiles one deterministic CL packet from:

- one CL historical source file
- one CL contract-extension source file containing only the remaining qualitative extension fields
- one minimal manual overlay containing only `contract`, `challenge_state`, and `opening_type`

Copy-paste-safe CL compile command:

```bash
mkdir -p ./build
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.packet_compiler.cli \
  --contract CL \
  --historical-input tests/fixtures/compiler/cl_historical_input.valid.json \
  --overlay tests/fixtures/compiler/cl_overlay.assisted.valid.json \
  --extension-input tests/fixtures/compiler/cl_extension.valid.json \
  --output ./build/cl.packet.json
```

The CL historical source contract is:

- `contract`
- `timestamp`
- `current_price`
- `session_open`
- `prior_day_high`
- `prior_day_low`
- `prior_day_close`
- `overnight_high`
- `overnight_low`
- `current_session_vah`
- `current_session_val`
- `current_session_poc`
- `previous_session_vah`
- `previous_session_val`
- `previous_session_poc`
- `vwap`
- `session_range`
- `avg_20d_session_range`
- `cumulative_delta`
- `current_volume_vs_average`
- `event_calendar_remainder`

The CL extension source contract is:

- `contract`
- `eia_timing`
- `oil_specific_headlines`
- `liquidity_sweep_summary`
- `dom_liquidity_summary`

In the current end state:

- `eia_timing` may still be supplied fixture-backed for the deterministic path, or provider-backed
  with `--eia-source eia`
- `realized_volatility_context` is no longer part of the CL extension fixture
- the remaining qualitative CL extension fields stay fixture-backed by design in compiler v1

The deterministic CL path preserves the same intentional manual boundary as ES for:

- `challenge_state`
- `opening_type`

### Databento-backed CL historical path

The fixture-backed CL path remains the deterministic default for tests, CI, and offline operator
verification.

To source only the CL historical market input from Databento instead, provide:

- `DATABENTO_API_KEY` in the shell environment
- a Databento request JSON such as
  `tests/fixtures/compiler/cl_databento_request.valid.json`
- the same fixture-backed CL extension input, because CL extension sourcing is not provider-backed
  in this slice

Copy-paste-safe CL Databento compile command:

```bash
export DATABENTO_API_KEY=your_existing_key
mkdir -p ./build
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.packet_compiler.cli \
  --contract CL \
  --historical-source databento \
  --databento-request tests/fixtures/compiler/cl_databento_request.valid.json \
  --overlay tests/fixtures/compiler/cl_overlay.assisted.valid.json \
  --extension-input tests/fixtures/compiler/cl_extension.valid.json \
  --output ./build/cl.packet.json
```

CL Databento request contract:

- `contract`
- `dataset`
- `symbol`
- `stype_in`
- `current_session_date`
- `bar_schema`
- `trades_schema`

The Databento-backed CL historical source:

- requires `DATABENTO_API_KEY`
- only supports `bar_schema=ohlcv-1m` and `trades_schema=trades`
- derives CL market fields from Databento bars and trades
- fails closed on malformed provider responses, missing current CL RTH coverage, missing prior CL
  session coverage, missing overnight coverage, unusable trade coverage, or ambiguous symbol
  coverage
- currently maps `event_calendar_remainder` to an empty list in the provider-backed CL historical
  path because CL calendar sourcing is not separated yet in this slice

### Provider-backed CL `eia_timing` path

The CL extension input remains fixture-backed by default.

To source only `eia_timing` from the EIA API while keeping the rest of the CL extension fixture-
backed, provide:

- `EIA_API_KEY` in the shell environment
- a CL EIA request JSON such as `tests/fixtures/compiler/cl_eia_request.valid.json`
- the same fixture-backed CL extension file for the remaining non-EIA extension fields

Copy-paste-safe CL EIA-backed command:

```bash
export EIA_API_KEY=your_existing_key
mkdir -p ./build
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.packet_compiler.cli \
  --contract CL \
  --historical-input tests/fixtures/compiler/cl_historical_input.valid.json \
  --overlay tests/fixtures/compiler/cl_overlay.assisted.valid.json \
  --extension-input tests/fixtures/compiler/cl_extension.valid.json \
  --eia-source eia \
  --eia-request tests/fixtures/compiler/cl_eia_request.valid.json \
  --output ./build/cl.packet.json
```

CL EIA request contract:

- `contract`
- `current_session_timestamp`
- `scheduled_release_time`
- `release_week_ending`
- `route`
- `facets`

The provider-backed CL `eia_timing` mapping is:

- if the EIA response confirms the requested `release_week_ending` and the current session
  timestamp is at or after `scheduled_release_time`, map to:
  - `status = "released"`
  - `scheduled_time = scheduled_release_time`
  - `minutes_since = floor((current_session_timestamp - scheduled_release_time) / 60s)`
- if the EIA response does not confirm the requested `release_week_ending` and the current session
  timestamp is before `scheduled_release_time`, map to:
  - `status = "scheduled"`
  - `scheduled_time = scheduled_release_time`
  - `minutes_until = floor((scheduled_release_time - current_session_timestamp) / 60s)`
- any other combination is treated as ambiguous and fails closed

The EIA-backed CL timing source:

- requires `EIA_API_KEY`
- only supports same-day session vs release interpretation
- fails closed on malformed provider responses, missing API key, multiple returned rows,
  mismatched response periods, or ambiguous pre/post-release interpretation

CL `realized_volatility_context` is no longer fixture-backed in the compiler path.

It is derived from:

- `session_range`
- `avg_20d_session_range`

Algorithm:

- compute `session_range / avg_20d_session_range`
- if ratio `>= 1.2`, map to `elevated`
- if ratio `<= 0.6`, map to `compressed`
- otherwise map to `normal`

The compiler fails closed if the required historical inputs for this derivation are malformed.

### 6E boundary summary

The current 6E compiler boundary is:

- provider-backed:
  - 6E historical market input via Databento, optionally
- upstream-derived from 6E historical segment bars:
  - `asia_high_low`
  - `london_high_low`
  - `ny_high_low_so_far`
- fixture-backed:
  - `dxy_context`
  - `europe_initiative_status`
- manual:
  - `challenge_state`
  - `opening_type`

Copy-paste-safe 6E compile command:

```bash
mkdir -p ./build
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.packet_compiler.cli \
  --contract 6E \
  --historical-input tests/fixtures/compiler/6e_historical_input.valid.json \
  --overlay tests/fixtures/compiler/6e_overlay.assisted.valid.json \
  --extension-input tests/fixtures/compiler/6e_extension.valid.json \
  --output ./build/6e.packet.json
```

Copy-paste-safe 6E Databento historical compile command:

```bash
export DATABENTO_API_KEY=your_existing_key
mkdir -p ./build
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.packet_compiler.cli \
  --contract 6E \
  --historical-source databento \
  --databento-request tests/fixtures/compiler/6e_databento_request.valid.json \
  --overlay tests/fixtures/compiler/6e_overlay.assisted.valid.json \
  --extension-input tests/fixtures/compiler/6e_extension.valid.json \
  --output ./build/6e.databento.packet.json
```

The 6E historical source contract is:

- `contract`
- `timestamp`
- `current_price`
- `session_open`
- `prior_day_high`
- `prior_day_low`
- `prior_day_close`
- `overnight_high`
- `overnight_low`
- `current_session_vah`
- `current_session_val`
- `current_session_poc`
- `previous_session_vah`
- `previous_session_val`
- `previous_session_poc`
- `vwap`
- `session_range`
- `avg_20d_session_range`
- `cumulative_delta`
- `current_volume_vs_average`
- `asia_bars`
- `london_bars`
- `ny_bars`
- `event_calendar_remainder`

The 6E Databento historical request contract is:

- `contract`
- `dataset`
- `symbol`
- `stype_in`
- `current_session_date`
- `bar_schema`
- `trades_schema`

The 6E extension source contract is:

- `contract`
- `dxy_context`
- `europe_initiative_status`

The 6E manual overlay contract is:

- `contract`
- `challenge_state`
- `opening_type`

Only the 6E historical market input is provider-backed in the current slice.

The remaining 6E contextual boundary is intentionally unchanged:

- fixture-backed:
  - `dxy_context`
  - `europe_initiative_status`
- manual:
  - `challenge_state`
  - `opening_type`

The 6E session-structure derivation rules are explicit and contract-local:

- `asia_high_low` uses `max(high)` and `min(low)` across `asia_bars`
- `london_high_low` uses `max(high)` and `min(low)` across `london_bars`
- `ny_high_low_so_far` uses `max(high)` and `min(low)` across `ny_bars`
- all three bar sets must be non-empty, strictly timestamp-ascending, duplicate-free, on the same UTC date as the historical `timestamp`, and ordered Asia then London then NY
- `ny_bars` must end at or before the historical `timestamp`

The 6E Databento historical source is fail-closed:

- requires `DATABENTO_API_KEY`
- supports only `bar_schema=ohlcv-1m` and `trades_schema=trades`
- requires current-date Asia, London, and NY bar coverage
- requires 20 completed prior 6E NY sessions
- requires usable current and previous 6E NY trade coverage for profile derivation
- rejects malformed records, missing timestamps, missing symbol coverage, or ambiguous trade-side input

The compiler fails closed if either `challenge_state` or `opening_type` is omitted from the manual overlay.
It also fails closed if either fixture-backed extension field, `dxy_context` or `europe_initiative_status`, is omitted.

### MGC boundary summary

The current MGC compiler boundary is:

- provider-backed:
  - MGC historical market input via Databento, optionally
- fixture-backed:
  - `dxy_context`
  - `yield_context`
  - `macro_fear_catalyst_summary`
- optional fixture-backed:
  - `swing_penetration_volume_summary`
- manual:
  - `challenge_state`
  - `opening_type`

Copy-paste-safe MGC compile command:

```bash
mkdir -p ./build
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.packet_compiler.cli \
  --contract MGC \
  --historical-input tests/fixtures/compiler/mgc_historical_input.valid.json \
  --overlay tests/fixtures/compiler/mgc_overlay.assisted.valid.json \
  --extension-input tests/fixtures/compiler/mgc_extension.valid.json \
  --output ./build/mgc.packet.json
```

Copy-paste-safe MGC Databento historical compile command:

```bash
export DATABENTO_API_KEY=your_existing_key
mkdir -p ./build
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.packet_compiler.cli \
  --contract MGC \
  --historical-source databento \
  --databento-request tests/fixtures/compiler/mgc_databento_request.valid.json \
  --overlay tests/fixtures/compiler/mgc_overlay.assisted.valid.json \
  --extension-input tests/fixtures/compiler/mgc_extension.valid.json \
  --output ./build/mgc.databento.packet.json
```

The MGC historical source contract is:

- `contract`
- `timestamp`
- `current_price`
- `session_open`
- `prior_day_high`
- `prior_day_low`
- `prior_day_close`
- `overnight_high`
- `overnight_low`
- `current_session_vah`
- `current_session_val`
- `current_session_poc`
- `previous_session_vah`
- `previous_session_val`
- `previous_session_poc`
- `vwap`
- `session_range`
- `avg_20d_session_range`
- `cumulative_delta`
- `current_volume_vs_average`
- `event_calendar_remainder`

The MGC extension source contract is:

- `contract`
- `dxy_context`
- `yield_context`
- `swing_penetration_volume_summary`
- `macro_fear_catalyst_summary`

The MGC manual overlay contract is:

- `contract`
- `challenge_state`
- `opening_type`

The MGC Databento historical request contract is:

- `contract`
- `dataset`
- `symbol`
- `stype_in`
- `current_session_date`
- `bar_schema`
- `trades_schema`

The MGC Databento historical source is fail-closed:

- requires `DATABENTO_API_KEY`
- supports only `bar_schema=ohlcv-1m` and `trades_schema=trades`
- requires current MGC RTH coverage
- requires 20 completed prior MGC RTH sessions
- requires usable current and previous MGC RTH trade coverage for profile derivation
- rejects malformed records, missing timestamps, missing symbol coverage, or ambiguous trade-side input

The compiler fails closed if either `challenge_state` or `opening_type` is omitted from the manual overlay.
It also fails closed if any required fixture-backed extension field, `dxy_context`, `yield_context`, or `macro_fear_catalyst_summary`, is omitted.
`swing_penetration_volume_summary` remains optional, fixture-backed, and nullable.

### NQ boundary summary

The current NQ compiler boundary is:

- fixture-backed:
  - `megacap_leadership_table`
- upstream-derived:
  - `relative_strength_vs_es` from NQ plus ES comparative market input
- provider-backed:
  - NQ historical market input via Databento, optionally
- manual:
  - `challenge_state`
  - `opening_type`

Copy-paste-safe NQ compile command:

```bash
mkdir -p ./build
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.packet_compiler.cli \
  --contract NQ \
  --historical-input tests/fixtures/compiler/nq_historical_input.valid.json \
  --overlay tests/fixtures/compiler/nq_overlay.assisted.valid.json \
  --relative-strength-input tests/fixtures/compiler/nq_relative_strength.valid.json \
  --extension-input tests/fixtures/compiler/nq_extension.valid.json \
  --output ./build/nq.packet.json
```

The NQ historical source contract is:

- `contract`
- `timestamp`
- `current_price`
- `session_open`
- `prior_day_high`
- `prior_day_low`
- `prior_day_close`
- `overnight_high`
- `overnight_low`
- `current_session_vah`
- `current_session_val`
- `current_session_poc`
- `previous_session_vah`
- `previous_session_val`
- `previous_session_poc`
- `vwap`
- `session_range`
- `avg_20d_session_range`
- `cumulative_delta`
- `current_volume_vs_average`
- `event_calendar_remainder`

The NQ relative-strength comparison contract is:

- `contract`
- `es_timestamp`
- `es_current_price`
- `es_session_open`

The NQ extension source contract is:

- `contract`
- `megacap_leadership_table`

`megacap_leadership_table` remains fixture-backed in the current NQ compiler boundary.

The NQ manual overlay contract is:

- `contract`
- `challenge_state`
- `opening_type`

`challenge_state` remains manual by design, and `opening_type` remains manual because the compiler
does not infer opening classification from market data.

The fixture-backed path above remains the deterministic default for tests, CI, and offline operator
verification.

To source only the NQ historical input from Databento instead, provide:

- `DATABENTO_API_KEY` in the shell environment
- a Databento request JSON such as
  `tests/fixtures/compiler/nq_databento_request.valid.json`

Copy-paste-safe Databento-backed NQ compile command:

```bash
export DATABENTO_API_KEY=your_existing_key
mkdir -p ./build
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.packet_compiler.cli \
  --contract NQ \
  --historical-source databento \
  --databento-request tests/fixtures/compiler/nq_databento_request.valid.json \
  --overlay tests/fixtures/compiler/nq_overlay.assisted.valid.json \
  --relative-strength-input tests/fixtures/compiler/nq_relative_strength.valid.json \
  --extension-input tests/fixtures/compiler/nq_extension.valid.json \
  --output ./build/nq.packet.json
```

NQ Databento request contract:

- `contract`
- `dataset`
- `symbol`
- `stype_in`
- `current_session_date`
- `bar_schema`
- `trades_schema`

The Databento-backed NQ historical source:

- requires `DATABENTO_API_KEY`
- only supports `bar_schema=ohlcv-1m` and `trades_schema=trades`
- maps provider data into:
  - current price
  - session open
  - prior day high / low / close
  - overnight high / low
  - current session VAH / VAL / POC
  - previous session VAH / VAL / POC
  - VWAP
  - session range
  - avg_20d_session_range
  - cumulative_delta
  - current_volume_vs_average
- fails closed on malformed provider responses, incomplete 20-session coverage, unsupported request
  inputs, or ambiguous symbol coverage

The compiler derives `relative_strength_vs_es` as:

- `(NQ current_price / NQ session_open) / (ES current_price / ES session_open)`

The comparative input must use the same timestamp as the NQ historical input, and the compiler
fails closed on malformed or non-positive ES comparison values.

Remaining NQ extension fields stay fixture-backed in this slice:

- `megacap_leadership_table`

The compiler fails closed if either `challenge_state` or `opening_type` is omitted from the manual
overlay.

### ZN boundary summary

The current ZN compiler boundary is:

- fixture-backed:
  - one ZN historical source file
  - `treasury_auction_schedule`
  - `macro_release_context`
  - `absorption_summary`
- provider-backed:
  - `cash_10y_yield` via FRED, optionally
- manual:
  - `challenge_state`
  - `opening_type`

Copy-paste-safe ZN compile command:

```bash
mkdir -p ./build
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.packet_compiler.cli \
  --contract ZN \
  --historical-input tests/fixtures/compiler/zn_historical_input.valid.json \
  --overlay tests/fixtures/compiler/zn_overlay.assisted.valid.json \
  --extension-input tests/fixtures/compiler/zn_extension.valid.json \
  --output ./build/zn.packet.json
```

The ZN historical source contract is:

- `contract`
- `timestamp`
- `current_price`
- `session_open`
- `prior_day_high`
- `prior_day_low`
- `prior_day_close`
- `overnight_high`
- `overnight_low`
- `current_session_vah`
- `current_session_val`
- `current_session_poc`
- `previous_session_vah`
- `previous_session_val`
- `previous_session_poc`
- `vwap`
- `session_range`
- `avg_20d_session_range`
- `cumulative_delta`
- `current_volume_vs_average`
- `event_calendar_remainder`

The ZN extension source contract is:

- `contract`
- `cash_10y_yield`
- `treasury_auction_schedule`
- `macro_release_context`
- `absorption_summary`

The ZN manual overlay contract is:

- `contract`
- `challenge_state`
- `opening_type`

ZN `cash_10y_yield` can optionally come from FRED while the rest of the ZN extension stays
fixture-backed.

Copy-paste-safe ZN compile command with FRED-backed `cash_10y_yield`:

```bash
export FRED_API_KEY=your_existing_key
mkdir -p ./build
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.packet_compiler.cli \
  --contract ZN \
  --historical-input tests/fixtures/compiler/zn_historical_input.valid.json \
  --overlay tests/fixtures/compiler/zn_overlay.assisted.valid.json \
  --extension-input tests/fixtures/compiler/zn_extension.valid.json \
  --cash-10y-yield-source fred \
  --fred-request tests/fixtures/compiler/zn_fred_cash_10y_yield_request.valid.json \
  --output ./build/zn.packet.json
```

FRED request contract:

- `contract`
- `observation_date`
- `series_id`

FRED query parameters used by the compiler:

- `series_id`
- `observation_start`
- `observation_end`
- `api_key`
- `file_type=json`

The FRED-backed `cash_10y_yield` source:

- requires `FRED_API_KEY`
- expects exactly one observation for the requested `observation_date`
- maps `observations[0].value` directly to `cash_10y_yield`
- fails closed on malformed responses, missing values, non-numeric values, or date mismatches

Remaining ZN extension fields stay fixture-backed in this slice:

- `treasury_auction_schedule`
- `macro_release_context`
- `absorption_summary`

The compiler fails closed if either `challenge_state` or `opening_type` is omitted from the manual
overlay.

The compiler also does not auto-derive:

- `treasury_auction_schedule`
- `macro_release_context`
- `absorption_summary`

Profile algorithm summary:

- POC is the highest-volume price in the session profile
- if multiple prices tie for highest volume, the compiler chooses the one closest to the session
  profile midpoint, then the lower price
- value area target is `70%` of total session profile volume
- starting from POC, the compiler expands outward one adjacent price level at a time
- at each step it adds the side with the higher next-level volume
- if both sides tie, it prefers the side closer to the session midpoint, then the lower side
- resulting `VAL` is the lowest included price and `VAH` is the highest included price

20-day range algorithm summary:

- input is `prior_20_rth_sessions`
- each session contributes `high - low`
- `avg_20d_session_range` is the arithmetic mean of those 20 completed session ranges
- the compiler rejects missing, duplicate, insufficient, or prior-session-mismatched lookback input

Current volume vs average algorithm summary:

- current observed RTH volume is `sum(current_rth_bars.volume)`
- baseline input is `prior_20_rth_observed_volumes`
- each baseline entry must represent the observed volume from the same elapsed RTH window as the
  current session bars
- `current_volume_vs_average` is current observed volume divided by the arithmetic mean of those 20
  observed baseline volumes
- the compiler rejects missing, duplicate, insufficient, nonpositive, or date-misaligned baseline
  input

## Phase 1a: inspect the provenance artifact

Copy-paste-safe provenance inspection:

```bash
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python - <<'PY'
import json
from pathlib import Path

provenance = json.loads(Path("./build/es.packet.provenance.json").read_text())
print("compiler_schema:", provenance["compiler_schema"])
print("contract:", provenance["contract"])
print("derived_features:", sorted(provenance["derived_features"].keys()))
print("current_price_source:", provenance["field_provenance"]["market_packet.current_price"])
PY
```

## Phase 2: run the runtime CLI on the compiled packet

Copy-paste-safe runtime command:

```bash
export GEMINI_API_KEY=your_existing_key
mkdir -p ./logs
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.cli \
  --packet ./build/es.packet.json \
  --audit-log ./logs/ninjatradebuilder.audit.jsonl
```

- If `--packet` points to a multi-contract bundle like `tests/fixtures/packets.valid.json`, add
  `--contract ES`.
- `--evaluation-timestamp` is optional. If omitted, the CLI uses `market_packet.timestamp`.
- `--model` is optional. The default is `gemini-3.1-pro-preview`.
- `--audit-log` is optional. When supplied, the CLI appends one JSON record per run.
- Gemini requests are bounded by the centralized timeout and retry env vars above.

Aggregate local audit logs with:

```bash
env PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m ninjatradebuilder.audit_report \
  --audit-log ./logs/ninjatradebuilder.audit.jsonl
```

The report prints concise counts for:

- success vs failure
- termination_stage
- final_decision
- error_category
- requested_contract

Equivalent Python API form:

```python
import json
import os
from pathlib import Path

from google import genai

from ninjatradebuilder import run_pipeline, validate_historical_packet
from ninjatradebuilder.gemini_adapter import GeminiResponsesAdapter

packet = json.loads(Path("tests/fixtures/packets.valid.json").read_text())
es_packet = {
    "$schema": "historical_packet_v1",
    "challenge_state": packet["shared"]["challenge_state"],
    "attached_visuals": packet["shared"]["attached_visuals"],
    "contract_metadata": packet["contracts"]["ES"]["contract_metadata"],
    "market_packet": packet["contracts"]["ES"]["market_packet"],
    "contract_specific_extension": packet["contracts"]["ES"]["contract_specific_extension"],
}

validated_packet = validate_historical_packet(es_packet)
adapter = GeminiResponsesAdapter(
    client=genai.Client(api_key=os.environ["GEMINI_API_KEY"]),
    model="gemini-3.1-pro-preview",
)
result = run_pipeline(
    packet=validated_packet,
    evaluation_timestamp_iso=validated_packet.market_packet.timestamp.isoformat().replace("+00:00", "Z"),
    model_adapter=adapter,
)

print(result.termination_stage)
print(result.final_decision)
```

## What this path guarantees

- prompt-bound contract routing
- strict stage-by-stage schema validation
- fail-closed termination at the first valid no-go stage
- explicit final decision mapping at Stage D
- clear startup failure when `GEMINI_API_KEY` is missing
- bounded Gemini request policy with explicit timeout/retry behavior
- optional local JSONL audit record for operator debugging
- thin local aggregate audit report for recurring-run visibility

## What this path does not provide yet

- compiler support beyond `ES`
- automatic population of all overlay fields from a real market-data provider
- persistent audit sink beyond local JSONL operator logs
- broader structured observability beyond local file-based aggregation
- deployment-specific handler for Netlify or other serverless targets
