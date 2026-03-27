# NTB CLI Workspace

## Authoritative preserved source
- source/ntb_engine/ is the preserved NinjaTradeBuilder engine source.
- Its live pipeline spine remains authoritative.

## Authoritative docs
- docs/spec/watchman_premarket_spec.md is the authoritative Watchman and pre-market specification.
- docs/spec/sales_pitch.md is the authoritative operator-facing product doctrine.
- docs/architecture/adapter_contracts.md contains adapter guidance.

## Reference-only source
- reference/ntb_v3_idea/ is reference-only.
- It may inform product direction and UI ideas.
- It is not the authoritative architecture.

## New build target
- target/ntb_marimo_console/ is the only place new UI, adapter, state, and view-model code should be created.

## Build rule
- Preserve engine truth.
- Preserve fail-closed live pipeline semantics.
- Do not invent market logic in the UI.
