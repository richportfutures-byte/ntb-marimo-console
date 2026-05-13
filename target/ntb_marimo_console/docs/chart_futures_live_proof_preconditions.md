# CHART_FUTURES Live Proof Preconditions Audit

Checkpoint audited: `a57b0fa Record five-contract LEVELONE live result`

This audit answers whether the repository can currently produce direct Schwab `CHART_FUTURES` live proof for `ES`, `NQ`, `CL`, `6E`, and `MGC`.

No live run was performed. This audit did not inspect secret files, token files, credentials, auth payloads, account values, customer or correl values, streamer URLs, raw quote values, raw chart values, or raw streamer payloads.

## Verdict

**CHART_FUTURES proof is premature with the current implementation.**

The repo can honestly state that bounded five-contract `LEVELONE_FUTURES` live updates were received and counted in the recorded run. It cannot yet produce direct `CHART_FUTURES` proof from the current live runtime path.

Implementation work is required before a direct `CHART_FUTURES` live proof run is justified.

## Existing Support Surfaces

- `market_data/bar_builder.py` accepts normalized `CHART_FUTURES`-style bar mappings.
- `market_data/chart_bars.py` models completed one-minute bars, completed five-minute bars, building five-minute bars, bar readiness, and blocking reasons.
- `tests/test_chart_futures_bar_builder.py` proves fixture-safe bar validation, symbol mismatch blocking, excluded-contract blocking, completed-vs-building five-minute state, gap blocking, out-of-order blocking, and final target isolation.
- `live_observables/builder.py` can surface completed bar-derived metadata when `ContractBarState` is provided, and reports chart-derived fields as unavailable when no chart state exists.
- `scripts/capture_five_contract_live_proof.py` can create a sanitized manual artifact shape with `LEVELONE_FUTURES` and `CHART_FUTURES` rows, but it is an artifact generator, not a live chart collector.

## Missing Direct Live Proof Preconditions

- `OperatorSchwabStreamerSession.subscribe()` currently builds a `LEVELONE_FUTURES` subscription payload.
- `scripts/run_operator_live_runtime_rehearsal.py` builds live runtime config with `services_requested=("LEVELONE_FUTURES",)` only.
- `OperatorSchwabStreamerSession.dispatch_one()` routes parsed data entries into `SchwabStreamManager.ingest_message`; it does not route live chart frames into `ChartFuturesBarBuilder`.
- `extract_data_entries()` normalizes streamer data entries as cache messages with `message_type="quote"`. It does not parse Schwab `CHART_FUTURES` payloads into `open`, `high`, `low`, `close`, `volume`, `start_time`, `end_time`, and `completed` fields.
- `SchwabStreamManager` stores normalized stream cache records, but it is not a chart-bar cache and does not aggregate or own `ContractBarState`.
- The operator live runtime rehearsal counts distinct received contracts from stream cache records. It does not count completed one-minute or completed five-minute chart bars.

## Source Classification

Current chart bars are fixture-normalized or manually supplied normalized records. They are not derived from recorded `LEVELONE_FUTURES` proof, and they are not currently sourced from direct live Schwab `CHART_FUTURES` frames in the production streamer session.

`LEVELONE_FUTURES` proof must not be expanded into chart-bar proof, entitlement robustness, rollover robustness, full live-session Marimo usability, query readiness, or production release readiness.

## Completed vs Building Bar Evidence

The bar builder distinguishes:

- completed one-minute bars,
- completed five-minute bars after five complete one-minute bars are present,
- building five-minute bars when the current bucket is incomplete,
- blocked states for missing, mismatched, malformed, out-of-order, unsupported, excluded, stale, or gapped data.

A future live chart proof must report completed `CHART_FUTURES` bar evidence directly. A building bar or missing/gapped one-minute set is not sufficient for completed-bar proof.

## Query Readiness Boundary

Where query readiness requires bars, missing or unavailable chart-bar state must remain fail-closed. Existing fixture-safe surfaces treat chart-derived values as unavailable until `CHART_FUTURES` bar state is supplied, and the preserved engine remains the sole decision authority.

## Required Implementation Before Direct Proof

Before a direct `CHART_FUTURES` live proof run is justified, the repo needs a narrow implementation path that:

- builds a direct `CHART_FUTURES` subscription request without weakening the existing `LEVELONE_FUTURES` path,
- parses raw Schwab `CHART_FUTURES` data frames into sanitized normalized bar messages,
- routes those normalized bar messages into `ChartFuturesBarBuilder`,
- records per-contract completed one-minute and completed five-minute bar evidence without raw values or raw payloads,
- preserves explicit live opt-in, one-session discipline, no repeated login on refresh, no fixture fallback after live failure, and the 15-second minimum refresh floor,
- keeps `ES`, `NQ`, `CL`, `6E`, and `MGC` as the only final target universe,
- keeps `ZN` and `GC` excluded and never maps `MGC` to `GC`.

## Release Boundary

`CHART_FUTURES` live proof is not currently justified. Production release readiness remains premature until direct `CHART_FUTURES` delivery, full live-session Marimo usability, entitlement and rollover robustness, and all other audited release predicates are satisfied with sanitized repository evidence.
