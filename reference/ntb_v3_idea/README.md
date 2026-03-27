# Claudes-NTB

`Claudes-NTB` is the long-term product repository for the local `NinjaTradeBuilder-v3` delivery. This migration keeps the v3 operator-facing Marimo app intact while putting it under source control with minimal smoke coverage and product documentation.

## Operator Modes

The app exposes exactly three operator modes from `app.py`:

- `Pre-Market Brief`
- `Live Pipeline`
- `Readiness Matrix`

The Pre-Market Brief remains first-class and returns contract-specific:

- `Framework`
- `Current Structure`
- `Key Structural Levels`
- `Why It Matters`
- `Long Thesis`
- `Short Thesis`
- `Query Triggers`
- `Watch For`
- `Schema Fields Referenced`

## Repository Layout

- `app.py`: Marimo operator app entry point
- `pipeline/`: schemas, prompts, readiness logic, pre-market generation, live pipeline orchestration
- `data/sample_packet.json`: local sample bundle for smoke validation
- `tests/`: migration smoke coverage
- `docs/migration-from-local-v3.md`: migration record and known hardening gaps

## Launch

Use the checked-in application root as the startup path:

```bash
python app.py
```

Or launch it explicitly with Marimo:

```bash
marimo run app.py
```

The app expects `GEMINI_API_KEY` for `Pre-Market Brief` and `Live Pipeline`. `Readiness Matrix` runs without the API key.

## Tests

Smoke coverage is intentionally narrow and migration-focused:

- app import / startup surface
- pre-market brief generation with a mocked Gemini client
- required pre-market brief sections present in output

Run:

```bash
pytest
```

## Hardening Still Needed

- Move more risk and doctrine checks out of prompts and into deterministic Python validation.
- Tighten bundle and extension validation beyond the current loose `extensions` dict shape.
- Replace the notebook-local `sys.path` import workaround in `app.py` with a cleaner package entry path.
- Expand tests beyond smoke coverage into stage logic, readiness edge cases, and failure modes.
