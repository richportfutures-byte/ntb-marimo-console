# Migration Note

This repository was initialized from the local source folder:

`/Users/stu/Documents/NinjaTrading w AI/NinjaTradeBuilder-v3`

The goal of the migration is not a raw archive. The repo is intended to become the durable home for the product while preserving the operator-facing v3 delivery.

## Preserved Product Surface

The migrated app keeps these three operator modes as the primary interface:

1. `Pre-Market Brief`
2. `Live Pipeline`
3. `Readiness Matrix`

## Launch Path

The app entry point remains `app.py` at the repository root.

- `python app.py`
- `marimo run app.py`

## What Was Added During Migration

- Git ignore rules for local and generated artifacts
- Root README describing product surfaces and startup
- Minimal pytest smoke coverage
- A narrow guard in pre-market watchman-context formatting so missing packet age does not crash brief generation

## Smoke Coverage

Current tests cover:

- root app importability
- pre-market brief generation with a mocked Gemini response
- required pre-market sections existing in the parsed `PreMarketBrief`

## Known Fragile Areas

- Stage logic remains prompt-heavy and is not fully enforced in deterministic code.
- `app.py` still relies on a local `sys.path` insert to import `pipeline`.
- External LLM calls still require a live `GEMINI_API_KEY`; tests avoid network by mocking the client.
- Packet extensions are still weakly typed at the bundle boundary.
